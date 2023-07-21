import re
from copy import deepcopy
from typing import TYPE_CHECKING, Callable, Dict, Iterator, List, MutableMapping, Tuple, cast

from cowbird.config import (
    BIDIRECTIONAL_ARROW,
    LEFT_ARROW,
    MULTI_TOKEN,
    NAMED_TOKEN_REGEX,
    RIGHT_ARROW,
    get_all_configs,
    get_mapping_info,
    get_permissions_from_str,
    validate_sync_config,
    validate_sync_config_services
)
from cowbird.handlers.handler_factory import HandlerFactory
from cowbird.typedefs import (
    JSON,
    ConfigSegment,
    PermissionConfigItemType,
    PermissionData,
    PermissionDictType,
    PermissionResourceData,
    ResourceSegment,
    ResourceTree,
    SyncPointMappingType,
    SyncPointServicesType
)
from cowbird.utils import get_config_path, get_logger

if TYPE_CHECKING:
    from cowbird.handlers.impl.magpie import Magpie

TargetResourcePermissions = Dict[
    str,  # target_resource_key
    List[str]  # target_permission
]
PermissionMapping = MutableMapping[
    str,  # src_resource_key
    MutableMapping[
        str,  # src_permission
        TargetResourcePermissions,
    ]
]

LOGGER = get_logger(__name__)

SEGMENT_NAME_REGEX = r"[\w:-]+"

RES_NAMETYPE_SEPARATOR = "::"

PERMISSION_DEFAULT_ACCESS = "allow"
PERMISSION_DEFAULT_SCOPE = "recursive"


class Permission:
    """
    Define every property required to set a permission in Magpie.
    """

    def __init__(self,
                 service_name: str,
                 service_type: str,
                 resource_id: int,
                 resource_full_name: str,
                 name: str,
                 access: str,
                 scope: str,
                 user: str = None,
                 group: str = None
                 ) -> None:
        self.service_name = service_name
        self.service_type = service_type
        self.resource_id = resource_id
        self.resource_full_name = resource_full_name
        self.name = name
        self.access = access
        self.scope = scope
        self.user = user
        self.group = group

    def __eq__(self, other: "Permission") -> bool:  # type: ignore[override]
        return (self.service_name == other.service_name and
                self.service_type == other.service_type and
                self.resource_id == other.resource_id and
                self.resource_full_name == other.resource_full_name and
                self.name == other.name and
                self.access == other.access and
                self.scope == other.scope and
                self.user == other.user and
                self.group == other.group)

    def get_full_permission_value(self) -> str:
        """
        Returns the full permission value, consisting of the name-access-scope values.
        """
        return f"{self.name}-{self.access}-{self.scope}"


class SyncPoint:
    """
    A sync point contains services sharing resources via multiple APIs.

    It defines how the same resource is defined in
    each service and what are the mapping between permission accesses.
    """

    def __init__(self,
                 services: SyncPointServicesType,
                 permissions_mapping_list: SyncPointMappingType,
                 ) -> None:
        """
        Init the sync point, holding services with their respective resources root and how access are mapped between
        them.

        :param services: Dict containing the resource keys by service type and all the names/types of each segment of
                         those resource keys
        :param permissions_mapping_list: List of strings representing a permission mapping between two resource keys
        """
        self.services: SyncPointServicesType = services
        self.resources = {res_key: res for svc in self.services.values() for res_key, res in svc.items()}

        # Save mapping config using this format:
        # {<src_resource_key> :
        #     {<src_permission> :
        #         {<target_resource_key> : [<target_permission>, ...],
        #           ...
        # }}}
        self.permissions_mapping: PermissionMapping = {}

        for mapping in permissions_mapping_list:
            left_res_key, left_permissions, direction, right_res_key, right_permissions = get_mapping_info(mapping)
            if direction in (BIDIRECTIONAL_ARROW, RIGHT_ARROW):
                self._add_mapping(left_res_key, left_permissions, right_res_key, right_permissions)
            if direction in (BIDIRECTIONAL_ARROW, LEFT_ARROW):
                self._add_mapping(right_res_key, right_permissions, left_res_key, left_permissions)

    @staticmethod
    def _get_explicit_permission(permission: str) -> str:
        """
        Converts a permission that could use an implicit format ('<name>' or '<name>-match') and converts it to use an
        explicit format ('<name>-<access>-<scope>').
        """
        permission_parts = permission.split("-")
        if len(permission_parts) == 1:
            return f"{permission}-{PERMISSION_DEFAULT_ACCESS}-{PERMISSION_DEFAULT_SCOPE}"
        if len(permission_parts) == 2 and permission_parts[1] == "match":
            return f"{permission_parts[0]}-{PERMISSION_DEFAULT_ACCESS}-match"
        if len(permission_parts) == 3:
            # Already in explicit form
            return permission
        raise RuntimeError(f"Invalid permission found: {permission}. Should either use the explicit format "
                           "`<name>-<access>-<scope>` or an implicit format `<name>` or `<name>-match`.")

    def _add_mapping(self, src_key: str, src_permissions: str, target_key: str, target_permissions: str) -> None:
        """
        Adds a source/target permission mapping to the object's permissions mapping.
        """
        if src_key not in self.permissions_mapping:
            self.permissions_mapping[src_key] = {}
        for src_permission in get_permissions_from_str(src_permissions):
            explicit_src_permission = SyncPoint._get_explicit_permission(src_permission)

            if explicit_src_permission not in self.permissions_mapping[src_key]:
                self.permissions_mapping[src_key][explicit_src_permission] = {}
            if target_key not in self.permissions_mapping[src_key][explicit_src_permission]:
                self.permissions_mapping[src_key][explicit_src_permission][target_key] = []

            for target_permission in get_permissions_from_str(target_permissions):
                self.permissions_mapping[src_key][explicit_src_permission][target_key].append(
                    SyncPoint._get_explicit_permission(target_permission))

    @staticmethod
    def _generate_regex_from_segments(res_segments: List[ConfigSegment]) -> Tuple[str, int]:
        """
        Generates a regex for a resource_nametype_path (ex.: /name1::type1/name2::type2) from a list of segments.

        Returns the regex along with the count of segments in the regex that are named. This count excludes tokenized
        segments.
        """
        named_segments_count = 0
        res_regex = r"^"
        for segment in res_segments:
            matched_groups = re.match(NAMED_TOKEN_REGEX, segment["name"])
            if matched_groups:
                # match any name with specific type 1 time only
                res_regex += (
                    rf"/(?P<{matched_groups.groups()[0]}>{SEGMENT_NAME_REGEX})"
                    rf"{RES_NAMETYPE_SEPARATOR}{segment['type']}"
                )
            elif segment["name"] == MULTI_TOKEN:
                # match any name with specific type, 0 or more times
                res_regex += rf"(?P<multi_token>(?:/{SEGMENT_NAME_REGEX}{RES_NAMETYPE_SEPARATOR}{segment['type']})*)"
            else:
                # match name and type exactly
                res_regex += rf"/{segment['name']}{RES_NAMETYPE_SEPARATOR}{segment['type']}"
                named_segments_count += 1
        res_regex += r"$"
        return res_regex, named_segments_count

    @staticmethod
    def _remove_type_from_nametype_path(nametype_path: str) -> str:
        """
        Removes the type from a nametype path (ex.: /name1::type1/name2::type2 becomes /name1/name2).
        """
        formatted_path = ""
        for segment in nametype_path.split("/"):
            if segment:
                formatted_path += "/" + segment.split(RES_NAMETYPE_SEPARATOR)[0]
        return formatted_path

    def _find_matching_res(self, service_type: str, resource_nametype_path: str) -> Tuple[str, Dict[str, str]]:
        """
        Finds a resource key that matches the input resource path, in the sync_permissions config. Note that it returns
        the longest match and only the named segments of the path are included in the length value. Any tokenized
        segment is ignored in the length.

        :param service_type: Type of the service associated with the input resource.
        :param resource_nametype_path: Full resource path name, which includes the type of each segment
                                       (ex.: /name1::type1/name2::type2)
        """
        if service_type in self.services:
            # Find which resource from the config matches with the input permission's resource tree
            # The length of a match is determined by the number of named segments matching the input resource.
            # Tokens are ignored from the match length since we favor a match with specific names over another with
            # generic tokens.
            #
            # Example cases:
            # 1:
            # - /dir1/**
            # - /dir1/dir2/dir3/** # We favor this path if it matches since it is more specific.
            # 2:
            # - /dir/file # We favor this path if it matches since it is more specific.
            # - /dir/{var}
            # 3:
            # Here both paths can match with the input resource_path `/file` and would result in an ambiguous match.
            # An error would be raised because 2 matches of the same length would be found.
            # - /**/file
            # - /file

            matched_length_by_res = {}
            matched_groups_by_res = {}
            service_resources = self.services[service_type]
            for res_key, res_segments in service_resources.items():
                res_regex, named_segments_count = SyncPoint._generate_regex_from_segments(res_segments)
                matches = re.match(res_regex, resource_nametype_path)
                if matches:
                    matched_groups = matches.groupdict()
                    if "multi_token" in matched_groups:
                        matched_groups["multi_token"] = SyncPoint._remove_type_from_nametype_path(
                            matched_groups["multi_token"]
                        )
                    matched_groups_by_res[res_key] = matched_groups
                    matched_length_by_res[res_key] = named_segments_count

            # Find the longest match
            max_match_len = max(matched_length_by_res.values(), default=0)
            max_matching_keys = [res for res, match_len in matched_length_by_res.items() if match_len == max_match_len]
            if len(max_matching_keys) == 1:
                src_res_key = max_matching_keys[0]
                return src_res_key, matched_groups_by_res[src_res_key]
            if len(max_matching_keys) > 1:
                raise ValueError("Found multiple matching resources of the same length in the config in the service "
                                 f"type {service_type}. Ambiguous config resources : {max_matching_keys}")

        # No matching resources could be found in the config file, return empty values.
        return "", {}

    @staticmethod
    def _create_res_data(target_segments: List[ConfigSegment],
                         input_matched_groups: Dict[str, str],
                         ) -> List[ResourceSegment]:
        """
        Creates resource data, by replacing any tokens found in the segment names to their actual corresponding values.
        This data includes the name and type of each segments of a full resource path.

        :param target_segments: List containing the name and type info of each segment of the target resource path.
        :param input_matched_groups:
        """
        res_data: List[ResourceSegment] = []
        for segment in target_segments:
            matched_groups = re.match(NAMED_TOKEN_REGEX, segment["name"])
            if matched_groups:
                res_data.append({
                    "resource_name": input_matched_groups[matched_groups.groups()[0]],
                    "resource_type": segment["type"]
                })
            elif segment["name"] == MULTI_TOKEN:
                multi_segments = input_matched_groups["multi_token"]
                # Skip the segment if the multi_token matched 0 times, resulting in an empty string.
                if multi_segments:
                    for seg in multi_segments.split("/"):
                        if seg:  # Ignore empty splits
                            res_data.append({
                                "resource_name": seg,
                                "resource_type": segment["type"]
                            })
            else:
                res_data.append({
                    "resource_name": segment["name"],
                    "resource_type": segment["type"]
                })
        return res_data

    def _get_resource_full_name_and_type(self,
                                         res_key: str,
                                         matched_groups: Dict[str, str],
                                         ) -> Tuple[str, List[ResourceSegment]]:
        """
        Finds the resource data from the config by using the resource key.

        Returns the formatted resource data along with the related service name.
        """
        # Get the resource_full_name, from the config, and with tokens
        svc_list = [s for s in self.services if res_key in self.services[s]]
        # Assume the service is the first found with the resource key, since the resource keys should be unique.
        svc_name = svc_list[0]
        target_segments = self.services[svc_name][res_key]
        res_data = SyncPoint._create_res_data(target_segments, matched_groups)
        return svc_name, res_data

    def _get_src_permissions(self) -> Iterator[Tuple[str, str]]:
        """
        Yields all source resource/permissions found in the mappings.
        """
        for src_res_key in self.permissions_mapping:  # pylint: disable=C0206,consider-using-dict-items
            for src_perm_name in self.permissions_mapping[src_res_key]:
                yield src_res_key, src_perm_name

    @staticmethod
    def _is_in_permissions(target_permission: str,
                           svc_name: str,
                           src_res_data: List[ResourceSegment],
                           permissions: JSON,
                           ) -> bool:
        """
        Checks if a target permission is found in a permissions dict.

        The check is done by looking for the target permission's resource path in the permissions dict.
        """
        if not permissions:
            return False

        resource = permissions[svc_name]
        is_service = True  # Used for the first iteration, which has a different structure
        res_access_key = "resources"
        for src_segment in src_res_data:
            if is_service:
                resource = resource[src_segment["resource_name"]]
                is_service = False  # Other children resources are not services
            else:
                for children_res in resource[res_access_key].values():
                    if children_res["resource_name"] == src_segment["resource_name"]:
                        resource = children_res
                        break
                else:
                    # Resource was not found, meaning the permission does not exist for the user or group.
                    return False
                # Use the 'children' key to access the rest of the resources
                res_access_key = "children"
        permission_names: List[str] = resource["permission_names"]
        return target_permission in permission_names

    def _filter_used_targets(self,
                             target_res_and_permissions: TargetResourcePermissions,
                             input_src_res_key: str,
                             src_matched_groups: Dict[str, str],
                             input_permission: Permission,
                             ) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        """
        Filters a dictionary of target resource/permissions, keeping only the permissions which should actually be
        removed.

        This is used for the `deleted` webhook event, where all target permissions should not necessarily be synced.
        Any target permission that is also a target permission in another mapping and where the source permission of
        that other mapping still exists, should not be synced yet, since it would destroy that other mapping.
        Ex.:

        .. code-block:: text

            A -> C
            B -> C

            or

            [A,B] -> C

        If the `A -> C` mapping was triggered for a `deleted` webhook event, the `C` target permission should
        only be synced if both `A` and `B` permissions don't exist.
        """

        handler = HandlerFactory().get_handler("Magpie")
        user_permissions = None
        grp_permissions = None
        user_targets = {}
        group_targets = {}
        if input_permission.user:
            user_permissions = handler.get_user_permissions(input_permission.user)
            user_targets = deepcopy(target_res_and_permissions)
        if input_permission.group:
            grp_permissions = handler.get_group_permissions(input_permission.group)
            group_targets = deepcopy(target_res_and_permissions)

        res_data: MutableMapping[str, Tuple[str, List[PermissionResourceData]]] = {}
        for src_res_key, src_perm_name in self._get_src_permissions():
            if src_res_key == input_src_res_key and src_perm_name == input_permission.get_full_permission_value():
                # No need to check the input src_key/permission, since it is the one that triggered the `deleted` event.
                # It is assumed no checks are required, since a webhook was received for this permission's deletion and
                # this permission should not exist anymore in Magpie.
                continue
            for target_res_key in target_res_and_permissions:
                if (target_res_key in self.permissions_mapping[src_res_key][src_perm_name]
                        and (target_res_key in user_targets or target_res_key in group_targets)):
                    for target_permission in target_res_and_permissions[target_res_key]:
                        if (target_permission in self.permissions_mapping[src_res_key][src_perm_name][target_res_key]
                                and (target_permission in user_targets.get(target_res_key, []) or
                                     target_permission in group_targets.get(target_res_key, []))):
                            # Another source resource uses the same target permission as the input.
                            # If the source permission exists, for the user/group, remove the target input permission
                            # since it should not be deleted in that case.
                            svc_name, src_res_data = res_data.get(
                                src_res_key,
                                self._get_resource_full_name_and_type(src_res_key, src_matched_groups)
                            )
                            # Save resource data if needed for other iterations
                            res_data[src_res_key] = (svc_name, src_res_data)
                            if (
                                target_permission in user_targets.get(target_res_key, []) and
                                SyncPoint._is_in_permissions(src_perm_name, svc_name, src_res_data, user_permissions)
                            ):
                                user_targets[target_res_key].remove(target_permission)
                                if not user_targets[target_res_key]:
                                    del user_targets[target_res_key]
                            if (
                                target_permission in group_targets.get(target_res_key, []) and
                                SyncPoint._is_in_permissions(src_perm_name, svc_name, src_res_data, grp_permissions)
                            ):
                                group_targets[target_res_key].remove(target_permission)
                                if not group_targets[target_res_key]:
                                    del group_targets[target_res_key]
        return user_targets, group_targets

    def _get_permission_data(self,
                             user_targets: Dict[str, List[str]],
                             group_targets: Dict[str, List[str]],
                             src_matched_groups: Dict[str, str],
                             input_permission: Permission) -> PermissionData:
        """
        Formats permissions data to send to Magpie. Output contains, for each target resource key, the resource path
        (with the name of each segment and its corresponding type), and all the permissions to sync, defining for each
        permission, if it is on a user, a group, or both.

        Output dict format :

        .. code-block:: json

            { <target_key>: {
                "res_path": [<list of segment names/types>],
                "permissions": { <permission_key>: [user, grp], ...}},
              ...
            }
        """
        permission_data: PermissionData = {}
        if input_permission.user:
            for target_key in user_targets:
                _, res_path = self._get_resource_full_name_and_type(target_key, src_matched_groups)
                permissions = {}
                for target_permission in user_targets[target_key]:
                    permissions[target_permission] = [input_permission.user, None]
                permission_data[target_key] = {"res_path": res_path, "permissions": permissions}
        if input_permission.group:
            for target_key in group_targets:
                if target_key not in permission_data:
                    _, res_path = self._get_resource_full_name_and_type(target_key, src_matched_groups)
                    permission_data[target_key] = {"res_path": res_path, "permissions": {}}
                for target_permission in group_targets[target_key]:
                    if target_permission in permission_data[target_key]["permissions"]:
                        permission_data[target_key]["permissions"][target_permission][1] = input_permission.group
                    else:
                        permission_data[target_key]["permissions"][target_permission] = [None, input_permission.group]
        return permission_data

    def _prepare_permissions_to_remove(self,
                                       target_res_and_permissions: TargetResourcePermissions,
                                       input_permission: Permission,
                                       input_src_res_key: str,
                                       src_matched_groups: Dict[str, str],
                                       ) -> PermissionData:
        """
        Removes every source resource found in the mappings that has an existing permission that is synced to one of the
        input target permissions.

        Used in the case of a `deleted` webhook event.
        """
        # If another mapping with the same target permission still has an existing source permission,
        # we can't remove the target permission yet.
        user_targets, group_targets = self._filter_used_targets(target_res_and_permissions, input_src_res_key,
                                                                src_matched_groups, input_permission)
        return self._get_permission_data(user_targets, group_targets, src_matched_groups, input_permission)

    def _find_permissions_to_sync(self,
                                  src_res_key: str,
                                  src_matched_groups: Dict[str, str],
                                  input_permission: Permission,
                                  perm_operation: Callable[[List[PermissionConfigItemType]], None],
                                  ) -> PermissionData:
        """
        Finds all permissions that should be synchronised with the source resource.
        """
        # Find each permission mapping related to source resource and input permission
        src_permissions = self.permissions_mapping.get(src_res_key)
        explicit_input_permission_name = input_permission.get_full_permission_value()
        target_res_and_permissions = src_permissions.get(explicit_input_permission_name) if src_permissions else None

        if not target_res_and_permissions:
            raise RuntimeError(f"Failed to find resource key {src_res_key} with permission "
                               f"{explicit_input_permission_name} from the config permissions_mapping.")

        permission_data = {}
        if perm_operation.__name__ == "delete_permission":
            permission_data = self._prepare_permissions_to_remove(
                target_res_and_permissions, input_permission, src_res_key, src_matched_groups)
        else:
            for target_key in target_res_and_permissions:
                _, res_path = self._get_resource_full_name_and_type(target_key, src_matched_groups)
                permissions = {}
                for target_permission in target_res_and_permissions[target_key]:
                    permissions[target_permission] = [input_permission.user, input_permission.group]
                permission_data[target_key] = {"res_path": res_path, "permissions": permissions}

        return permission_data

    def sync(self,
             perm_operation: Callable[[List[PermissionConfigItemType]], None],
             permission: Permission,
             src_resource_tree: ResourceTree,
             ) -> None:
        """
        Create or delete target permissions, that are mapped to the source resource that triggered the event.

        :param perm_operation: Magpie create_permission or delete_permission function
        :param permission: Permission to synchronize with others services
        :param src_resource_tree: Resource tree associated with the permission to synchronize
        """
        resource_nametype_path = ""
        for res in src_resource_tree:
            resource_nametype_path += f"/{res['resource_name']}{RES_NAMETYPE_SEPARATOR}{res['resource_type']}"

        src_res_key, src_matched_groups = self._find_matching_res(permission.service_type, resource_nametype_path)
        if not src_res_key:
            # A matching resource was not found in the sync config, nothing to do.
            return
        target_permissions = self._find_permissions_to_sync(src_res_key, src_matched_groups, permission, perm_operation)

        for target in target_permissions.values():
            permissions_data = target["res_path"]
            for perm_key, user_and_group, in target["permissions"].items():
                # add permission details to last segment
                permission_info = perm_key.split("-")
                if len(permission_info) != 3:
                    raise RuntimeError(f"Invalid permission found: {perm_key}. It should use the explicit "
                                       "format `<name>-<access>-<scope>`.")
                perm: PermissionDictType = dict(zip(["name", "access", "scope"], permission_info))
                perm_data = cast(PermissionConfigItemType, permissions_data[-1])
                perm_data["permission"] = perm
                perm_data["user"] = user_and_group[0]
                perm_data["group"] = user_and_group[1]
                perm_operation(permissions_data)


class PermissionSynchronizer(object):
    """
    Keep service-shared resources in sync when permissions are updated for one of them.

    .. todo:: At some point we will need a consistency function that goes through all permissions of all services and
              make sure that linked services have the same permissions.
    """

    def __init__(self, magpie_inst: "Magpie") -> None:
        config_path = get_config_path()
        sync_perm_cfgs = get_all_configs(config_path, "sync_permissions", allow_missing=True)
        self.sync_point = []
        self.magpie_inst = magpie_inst

        for sync_perm_config in sync_perm_cfgs:
            if not sync_perm_config:
                LOGGER.warning("Sync_permissions configuration is empty.")
                continue
            for sync_cfg in sync_perm_config.values():
                # Config should already be validated at cowbird startup, revalidate here since config gets reloaded
                validate_sync_config(sync_cfg)

                # Validate config services, only done here, since Magpie instance is not available at cowbird startup.
                available_services = self.magpie_inst.get_service_types()
                validate_sync_config_services(sync_cfg, available_services)

                services = sync_cfg["services"]
                perm_map = sync_cfg["permissions_mapping"]
                self.sync_point.append(SyncPoint(services=services, permissions_mapping_list=perm_map))

    def create_permission(self, permission: Permission) -> None:
        """
        Create the same permission on each service sharing the same resource.
        """
        resource_tree = cast(ResourceTree, self.magpie_inst.get_parents_resource_tree(permission.resource_id))
        for point in self.sync_point:
            point.sync(self.magpie_inst.create_permissions, permission, resource_tree)

    def delete_permission(self, permission: Permission) -> None:
        """
        Delete the same permission on each service sharing the same resource.
        """
        resource_tree = cast(ResourceTree, self.magpie_inst.get_parents_resource_tree(permission.resource_id))
        for point in self.sync_point:
            point.sync(self.magpie_inst.delete_permission, permission, resource_tree)
