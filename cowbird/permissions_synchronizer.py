from copy import deepcopy
import re
from typing import TYPE_CHECKING

from cowbird.config import BIDIRECTIONAL_ARROW, LEFT_ARROW, MULTI_TOKEN, RIGHT_ARROW, \
    get_all_configs, get_mapping_info, get_permissions_from_str, validate_sync_config, NAMED_TOKEN_REGEX, \
    validate_sync_config_services
from cowbird.services.service_factory import ServiceFactory
from cowbird.utils import get_config_path, get_logger

if TYPE_CHECKING:
    from typing import Callable, Dict, Generator, List, Tuple

    from cowbird.services.impl.magpie import Magpie

    SyncPointServicesType = Dict[str, Dict[str, List[Dict[str, str]]]]
    SyncPointMappingType = List[str]

LOGGER = get_logger(__name__)

SEGMENT_NAME_REGEX = r"[\w:-]+"

RES_NAMETYPE_SEPARATOR = "::"


class Permission:
    """
    Define every property required to set a permission in Magpie.
    """

    def __init__(self,
                 service_name,        # type: str
                 resource_id,         # type: str
                 resource_full_name,  # type: str
                 name,                # type: str
                 access,              # type: str
                 scope,               # type: str
                 user=None,           # type: str
                 group=None           # type: str
                 ):                   # type: (...) -> None
        self.service_name = service_name
        self.resource_id = resource_id
        self.resource_full_name = resource_full_name
        self.name = name
        self.access = access
        self.scope = scope
        self.user = user
        self.group = group

    def __eq__(self, other):
        # type: (Permission) -> bool
        return (self.service_name == other.service_name and
                self.resource_id == other.resource_id and
                self.resource_full_name == other.resource_full_name and
                self.name == other.name and
                self.access == other.access and
                self.scope == other.scope and
                self.user == other.user and
                self.group == other.group)


class SyncPoint:
    """
    A sync point contains services sharing resources via multiple APIs.

    It defines how the same resource is defined in
    each service and what are the mapping between permission accesses.
    """

    def __init__(self,
                 services,                 # type: SyncPointServicesType
                 permissions_mapping_list  # type: SyncPointMappingType
                 ):                        # type: (...) -> None
        """
        Init the sync point, holding services with their respective resources root and how access are mapped between
        them.

        :param services: Dict containing the resource keys by service and all the names/types of each segment of those
                         resource keys
        :param permissions_mapping_list: List of strings representing a permission mapping between two resource keys
        """
        self.services = {svc: svc_cfg for svc, svc_cfg in services.items()}
        self.resources = {res_key: res for svc in self.services.values() for res_key, res in svc.items()}

        # Save mapping config using this format:
        # {<src_resource_key> :
        #     {<src_permission> :
        #         {<target_resource_key> : [<target_permission>, ...],
        #           ...
        # }}}
        self.permissions_mapping = {}

        for mapping in permissions_mapping_list:
            res_key1, permission1, direction, res_key2, permission2 = get_mapping_info(mapping)
            if direction == BIDIRECTIONAL_ARROW or direction == RIGHT_ARROW:
                self._add_mapping(res_key1, permission1, res_key2, permission2)
            if direction == BIDIRECTIONAL_ARROW or direction == LEFT_ARROW:
                self._add_mapping(res_key2, permission2, res_key1, permission1)

    def _add_mapping(self, src_key, src_permissions, target_key, target_permissions):
        # type: (str, str, str, str) -> None
        """
        Adds a source/target permission mapping to the object's permissions mapping.
        """
        if src_key not in self.permissions_mapping:
            self.permissions_mapping[src_key] = {}
        for permission in get_permissions_from_str(src_permissions):
            if permission not in self.permissions_mapping[src_key]:
                self.permissions_mapping[src_key][permission] = {}
            if target_key not in self.permissions_mapping[src_key][permission]:
                self.permissions_mapping[src_key][permission][target_key] = []

            self.permissions_mapping[src_key][permission][target_key] += \
                get_permissions_from_str(target_permissions)

    @staticmethod
    def _generate_regex_from_segments(res_segments):
        # type: (List[Dict[str, str]]) -> (str, int)
        """
        Generates a regex for a resource_nametype_path (ex.: /name1::type1/name2::type2) from a list of segments.
        Returns the regex along with the count of segments in the regex that are named, and not using any token.
        """
        named_segments_count = 0
        res_regex = r"^"
        for segment in res_segments:
            matched_groups = re.match(NAMED_TOKEN_REGEX, segment["name"])
            if matched_groups:
                # match any name with specific type 1 time only
                res_regex += rf"/(?P<{matched_groups.groups()[0]}>{SEGMENT_NAME_REGEX})" \
                             rf"{RES_NAMETYPE_SEPARATOR}{segment['type']}"
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
    def _remove_type_from_nametype_path(nametype_path):
        # type: (str) -> str
        """
        Removes the type from a nametype path (ex.: /name1::type1/name2::type2 becomes /name1/name2).
        """
        formatted_path = ""
        for segment in nametype_path.split("/"):
            if segment:
                formatted_path += "/" + segment.split(RES_NAMETYPE_SEPARATOR)[0]
        return formatted_path

    def _find_matching_res(self, service_name, resource_nametype_path):
        # type: (str, str) -> (str, Dict[str, str])
        """
        Finds a resource key that matches the input resource path, in the sync_permissions config.
        Note that it returns the longest match and only the named segments of the path are included in the length value.
        Any tokenized segment is ignored in the length.

        :param service_name: Name of the service associated with the input resource.
        :param resource_nametype_path: Full resource path name, which includes the type of each segment
                                       (ex.: /name1::type1/name2::type2)
        """
        service_resources = self.services[service_name]
        # Find which resource from the config matches with the input permission's resource tree
        # The length of a match is determined by the number of named segments matching the input resource.
        # Tokens are ignored from the match length since we favor a match with specific names over another with
        # generic tokens.
        matched_length_by_res = {}
        matched_groups_by_res = {}
        for res_key, res_segments in service_resources.items():
            res_regex, named_segments_count = SyncPoint._generate_regex_from_segments(res_segments)
            matched_groups = re.match(res_regex, resource_nametype_path)
            if matched_groups:
                matched_groups = matched_groups.groupdict()
                if "multi_token" in matched_groups:
                    matched_groups["multi_token"] = \
                        SyncPoint._remove_type_from_nametype_path(matched_groups["multi_token"])
                matched_groups_by_res[res_key] = matched_groups
                matched_length_by_res[res_key] = named_segments_count

        # Find the longest match
        max_match_len = max(matched_length_by_res.values())
        max_matching_keys = [res for res, match_len in matched_length_by_res.items() if match_len == max_match_len]
        if len(max_matching_keys) == 1:
            src_res_key = max_matching_keys[0]
        elif len(max_matching_keys) > 1:
            raise ValueError("Found 2 matching resources of the same length in the config. Ambiguous config resources :"
                             f" {max_matching_keys}")
        else:
            raise ValueError("No matching resources could be found in the config file.")
        return src_res_key, matched_groups_by_res[src_res_key]

    @staticmethod
    def _create_res_data(target_segments, input_matched_groups):
        # type: (List[Dict], Dict[str, str]) -> List[Dict]
        """
        Creates resource data, by replacing any tokens found in the segment names to their actual corresponding values.
        This data includes the name and type of each segments of a full resource path.

        :param target_segments: List containing the name and type info of each segment of the target resource path.
        :param matched_groups:
        """
        res_data = []
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

    def _get_resource_full_name_and_type(self, res_key, matched_groups):
        # type: (str, Dict[str, str]) -> (str, List[Dict])
        """
        Finds the resource data from the config by using the resource key.
        Returns the formatted resource data along with the related service name.
        """
        # Get the resource_full_name, from the config, and with tokens
        svc_list = [s for s in self.services if res_key in self.services[s]]
        # Assume the service is the first found with the resource key, since the resource keys should be unique.
        svc_name = svc_list[0]
        target_segments = self.services[svc_name][res_key]
        return svc_name, SyncPoint._create_res_data(target_segments, matched_groups)

    def _get_src_permissions(self):
        # type: () -> Generator[Tuple[str, str]]
        """
        Yields all source resource/permissions found in the mappings.
        """
        for src_res_key in self.permissions_mapping:
            for src_perm_name in self.permissions_mapping[src_res_key]:
                yield src_res_key, src_perm_name

    @staticmethod
    def _is_in_permissions(target_permission, svc_name, src_res_full_name, permissions):
        # type: (str, str, str, Dict) -> bool
        """
        Checks if a target permission is found in a permissions dict.
        The check if done by looking for the target permission's resource path in the permissions dict.
        """
        resource = permissions[svc_name]
        is_service = True  # Used for the first iteration, which has a different structure
        res_access_key = "resources"
        for src_res in src_res_full_name:
            if is_service:
                resource = resource[src_res["resource_name"]]
                is_service = False  # Other children resources are not services
            else:
                for children_res in resource[res_access_key].values():
                    if children_res["resource_name"] == src_res["resource_name"]:
                        resource = children_res
                        break
                else:
                    # Resource was not found, meaning the permission does not exist for the user or group.
                    return False
                # Use the 'children' key to access the rest of the resources
                res_access_key = "children"
        return target_permission in resource["permission_names"]

    def _filter_used_targets(self, target_res_and_permissions, input_src_res_key, src_matched_groups, input_permission):
        # type: (Dict, str, Dict[str, str], Permission) -> (Dict, Dict)
        """
        Filters a dictionary of target resource/permissions. This is used for the `remove` permission case, where all
        target permissions should not necessarily be synched. Any target permission that is also a target permission in
        another mapping and where the source permission of that other mapping still exists, should not be synched yet,
        since it would destroy that other mapping.
        Ex.:
        A -> C
        B -> C
        If the A->C mapping was triggered for a `remove` permission case, the C target permission should only by synched
        if both A and B permissions don't exist.
        """

        svc = ServiceFactory().get_service("Magpie")
        user_permissions = None
        grp_permissions = None
        if input_permission.user:
            user_permissions = svc.get_user_permissions(input_permission.user)
        if input_permission.group:
            grp_permissions = svc.get_group_permissions(input_permission.group)

        user_targets = deepcopy(target_res_and_permissions)
        group_targets = deepcopy(target_res_and_permissions)
        res_data = {}
        for src_res_key, src_perm_name in self._get_src_permissions():
            if src_res_key == input_src_res_key:
                # No need to check the input src key, since it is the one that triggered the `remove` event.
                continue
            for target_res_key in target_res_and_permissions:
                if target_res_key in self.permissions_mapping[src_res_key][src_perm_name] \
                        and (target_res_key in user_targets or target_res_key in group_targets):
                    for target_permission in target_res_and_permissions[target_res_key]:
                        if target_permission in self.permissions_mapping[src_res_key][src_perm_name][target_res_key] \
                                and (target_permission in user_targets[target_res_key] or
                                     target_permission in group_targets[target_res_key]):
                            # Another source resource uses the same target permission as the input.
                            # If the source permission exists, for the user/group, remove the target input permission
                            # since it should not be deleted in that case.
                            svc_name, src_res_data = res_data.get(src_res_key,
                                                                  self._get_resource_full_name_and_type(src_res_key, src_matched_groups))
                            # Save resource data if needed for other iterations
                            res_data[src_res_key] = (svc_name, src_res_data)
                            if target_permission in user_targets[target_res_key] and \
                                    SyncPoint._is_in_permissions(src_perm_name, svc_name, src_res_data, user_permissions):
                                user_targets[target_res_key].remove(target_permission)
                                if not user_targets[target_res_key]:
                                    del user_targets[target_res_key]
                            if target_permission in group_targets[target_res_key] and \
                                  SyncPoint._is_in_permissions(src_perm_name, svc_name, src_res_data, grp_permissions):
                                group_targets[target_res_key].remove(target_permission)
                                if not group_targets[target_res_key]:
                                    del group_targets[target_res_key]
        return user_targets, group_targets

    def _get_permission_data(self, user_targets, group_targets, src_matched_groups, input_permission):
        # type: (Dict, Dict, Dict, Permission) -> Dict
        """
        Formats permissions data to send to Magpie. Output contains, for each target resource key, the resource path
        (with the name of each segment and its corresponding type), and all the permissions to sync, defining for each
        permission, if it is on a user, a group, or both.
        Output dict format :
        { <target_key>: {
            "res_path": [<list of segment names/types>],
            "permissions": { <permission_key>: [user, grp], ...}},
          ...
        }
        """
        permission_data = {}
        for target_key in user_targets:
            _, res_path = self._get_resource_full_name_and_type(target_key, src_matched_groups)
            permissions = {}
            for target_permission in user_targets[target_key]:
                permissions[target_permission] = [input_permission.user, None]
            permission_data[target_key] = {"res_path": res_path, "permissions": permissions}
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

    def _prepare_permissions_to_remove(self, target_res_and_permissions, input_permission, input_src_res_key,
                                       src_matched_groups):
        # type: (Dict[List], Permission, str, Dict) -> Dict
        """
        Removes every source resource found in the mappings that has an existing permission that is synched to one of
        the input target permissions. Used in the case of a `remove` permission.
        """
        # If another mapping with the same target permission still has an existing source permission,
        # we can't remove the target permission yet.
        user_targets, group_targets = self._filter_used_targets(target_res_and_permissions, input_src_res_key,
                                                                src_matched_groups, input_permission)
        return self._get_permission_data(user_targets, group_targets, src_matched_groups, input_permission)

    def _find_permissions_to_sync(self, src_res_key, src_matched_groups, input_permission, perm_operation):
        # type: (str, Dict, Permission, Callable[[List[Dict]], None]) -> Dict
        """
        Finds all permissions that should be synchronised with the source resource.
        """
        # For each permission mapping
        src_permissions = self.permissions_mapping.get(src_res_key)
        target_res_and_permissions = src_permissions.get(input_permission.name) if src_permissions else None

        if not target_res_and_permissions:
            raise RuntimeError(f"Failed to find resource key {src_res_key} with permission {input_permission.name}"
                               "from the config permissions_mapping.")

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

    def sync(self, perm_operation, permission, src_resource_tree):
        # type: (Callable[[List[Dict]], None], Permission, List[Dict]) -> None
        """
        Create or delete target permissions, that are mapped to the source resource that triggered the event.

        :param perm_operation: Magpie create_permission or delete_permission function
        :param permission: Permission to synchronize with others services
        :param src_resource_tree: Resource tree associated with the permission to synchronize
        """
        resource_nametype_path = ""
        for res in src_resource_tree:
            resource_nametype_path += f"/{res['resource_name']}{RES_NAMETYPE_SEPARATOR}{res['resource_type']}"

        src_res_key, src_matched_groups = self._find_matching_res(permission.service_name, resource_nametype_path)
        target_permissions = self._find_permissions_to_sync(src_res_key, src_matched_groups, permission, perm_operation)

        for target in target_permissions.values():
            permissions_data = target["res_path"]
            for perm_name, user_and_group, in target["permissions"].items():
                # add permission details to last segment
                permissions_data[-1]["permission"] = perm_name
                permissions_data[-1]["user"] = user_and_group[0]
                permissions_data[-1]["group"] = user_and_group[1]

                perm_operation(permissions_data)


class PermissionSynchronizer(object):
    """
    Keep service-shared resources in sync when permissions are updated for one of them.

    .. todo:: At some point we will need a consistency function that goes through all permissions of all services and
              make sure that linked services have the same permissions.
    """

    def __init__(self, magpie_inst):
        # type: (Magpie) -> None
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
                available_services = self.magpie_inst.get_service_names()
                validate_sync_config_services(sync_cfg, available_services)

                self.sync_point.append(SyncPoint(services=sync_cfg["services"],
                                                 permissions_mapping_list=sync_cfg["permissions_mapping"]))

    def create_permission(self, permission):
        # type: (Permission) -> None
        """
        Create the same permission on each service sharing the same resource.
        """
        resource_tree = self.magpie_inst.get_resources_tree(permission.resource_id)
        for point in self.sync_point:
            point.sync(self.magpie_inst.create_permission, permission, resource_tree)

    def delete_permission(self, permission):
        # type: (Permission) -> None
        """
        Delete the same permission on each service sharing the same resource.
        """
        resource_tree = self.magpie_inst.get_resources_tree(permission.resource_id)
        for point in self.sync_point:
            point.sync(self.magpie_inst.delete_permission, permission, resource_tree)
