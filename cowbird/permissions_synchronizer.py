import re
from typing import TYPE_CHECKING

from cowbird.config import BIDIRECTIONAL_ARROW, LEFT_ARROW, MULTI_TOKEN, RIGHT_ARROW, \
    get_all_configs, get_mapping_info, get_permissions_from_str, validate_sync_config, NAMED_TOKEN_REGEX
from cowbird.services.service_factory import ServiceFactory
from cowbird.utils import get_config_path, get_logger

if TYPE_CHECKING:
    from typing import Callable, Dict, Generator, List, Match, Tuple

    from cowbird.services.impl.magpie import Magpie

    SyncPointServicesType = Dict[str, str]
    SyncPointMappingType = List[str]

LOGGER = get_logger(__name__)

SEGMENT_NAME_REGEX = r"[\w:-]+"


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
    A sync point contain services sharing resources via multiple API.

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

        :param services: Dict, where the service is the key and its resources root is the value
        :param permissions_mapping_list: List of dict where the service is the key and an access list is the value
        """
        available_services = ServiceFactory().services_cfg.keys()
        # Make sure that only active services are used
        self.services = {svc: svc_cfg for svc, svc_cfg in services.items() if svc in available_services}
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
        if src_key not in self.permissions_mapping:
            self.permissions_mapping[src_key] = {}
        for permission in get_permissions_from_str(src_permissions):
            if permission not in self.permissions_mapping[src_key]:
                self.permissions_mapping[src_key][permission] = {}
            if target_key not in self.permissions_mapping[src_key][permission]:
                self.permissions_mapping[src_key][permission][target_key] = []

            self.permissions_mapping[src_key][permission][target_key] += \
                get_permissions_from_str(target_permissions)

    def get_src_permissions(self):
        # type: () -> Generator[Tuple[str, str]]
        """
        Yields all source resource/permissions found in the mappings.
        """
        for src_res_key in self.permissions_mapping:
            for src_perm_name in self.permissions_mapping[src_res_key]:
                yield src_res_key, src_perm_name

    def get_resource_full_name_and_type(self, res_key, matched_groups):
        # Get the resource_full_name, from the config, and with tokens
        svc_list = [s for s in self.services if res_key in self.services[s]]
        # Assume the service is the first found with the resource key, since the resource keys should be unique.
        svc_name = svc_list[0]
        target_segments = self.services[svc_name][res_key]
        return svc_name.lower(), SyncPoint._create_res_data(target_segments, matched_groups)

    def filter_used_targets(self, target_res_and_permissions, input_permission, input_src_res_key,
                            src_matched_groups):
        # type: (Dict[List], Permission, str, Match[str]) -> Dict
        """
        Removes every source resource found in the mappings that has an existing permission that is synched to one of
        the input target permissions. Used in the case of a `remove` permission.
        """

        def is_in_permissions(target_permission, svc_name, src_res_full_name, permissions):
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
            return target_permission in resource["permissions"]

        svc = ServiceFactory().get_service("Magpie")
        user_permissions = None
        group_permissions = None
        if input_permission.user:
            user_permissions = svc.get_user_permissions(input_permission.user)
        if input_permission.group:
            group_permissions = svc.get_group_permissions(input_permission.group)

        user_targets = target_res_and_permissions.copy()
        group_targets = target_res_and_permissions.copy()
        res_data = {}
        for src_res_key, src_perm_name in self.get_src_permissions():
            if src_res_key == input_src_res_key:
                # No need to check the input src key, since it is the one that triggered the `remove` event.
                continue
            for target_res_key, target_permissions in target_res_and_permissions.items():
                if target_res_key in self.permissions_mapping[src_res_key][src_perm_name] \
                        and (target_res_key in user_targets or target_res_key in group_targets):
                    for target_permission in target_permissions:
                        if target_permission in self.permissions_mapping[src_res_key][src_perm_name][target_res_key] \
                                and (target_permission in user_targets[target_res_key] or
                                     target_permission in group_targets[target_res_key]):
                            # Another source resource uses the same target permission as the input.
                            # If the source permission exists, for the user/group, remove the target input permission
                            # since it should not be deleted in that case.
                            svc_name, src_res_full_name = res_data.get(src_res_key,
                                                self.get_resource_full_name_and_type(src_res_key, src_matched_groups))
                            res_data[src_res_key] = (svc_name, src_res_full_name)
                            # TODO: fix usage of svc_name, how to know in what service is the resource,
                            #  do cowbird config service name correspond to magpie svc names --
                            #  No, do we add a field in the services config to know the mapping with Magpie?
                            if target_permission in user_targets[target_res_key] and is_in_permissions(src_perm_name, svc_name, src_res_full_name, user_permissions):
                                # remove from user_targets
                                user_targets[target_res_key].remove(target_permission)
                                if not user_targets[target_res_key]:
                                    del user_targets[target_res_key]
                            if target_permission in group_targets[target_res_key] and is_in_permissions(src_perm_name, svc_name, src_res_full_name, group_permissions):
                                # remove from group_targets
                                group_targets[target_res_key].remove(target_permission)
                                if not group_targets[target_res_key]:
                                    del group_targets[target_res_key]
        permission_data = {}
        # target_key: {res_path: [], permissions: [(), (), ..]}
        for target_key in user_targets:
            _, res_path = self.get_resource_full_name_and_type(target_key, src_matched_groups)
            permissions = []
            for target_permission in user_targets[target_key]:

                permissions.append([target_permission, input_permission.user, None])
            permission_data[target_key] = {"res_path": res_path, "permissions": permissions}
        for target_key in group_targets:
            # if target_key in permission_data:
            #     for target_permission in group_targets[target_key]:
            #         if target_permission in permission_data[target_key]
            #         permission_data[target_key]["permissions"][2] = input_permission.group
            # TODO: update permission_data with group_targets (if exists already, just add group_name, else create new entry)
            # Find better data structure
            pass
        return permission_data

    def find_permissions_to_sync(self, src_res_key, src_matched_groups, permission, perm_operation):
        # type: (str, Match[str], Permission, Callable[[List[Dict]], None]) -> Dict[List]
        """
        Search and yield for every match a (service, permission name) tuple that is mapped with this permission.
        """
        # For each permission mapping
        src_permissions = self.permissions_mapping.get(src_res_key)
        target_res_and_permissions = src_permissions.get(permission.name) if src_permissions else None

        permission_data = {}
        if target_res_and_permissions:
            if perm_operation.__name__ == "delete_permission":
                # If another mapping with the same target permission still has an existing source permission,
                # we can't remove the target permission yet.
                permission_data = self.filter_used_targets(
                    target_res_and_permissions, permission, src_res_key, src_matched_groups)
            else:
                for target_key in target_res_and_permissions:
                    _, res_path = self.get_resource_full_name_and_type(target_key, src_matched_groups)
                    permissions = []
                    for target_permission in target_res_and_permissions[target_key]:
                        permissions.append([target_permission, permission.user, permission.group])
                    permission_data[target_key] = {"res_path": res_path, "permissions": permissions}

        return permission_data

    def _find_matching_res(self, service_name, resource_nametype_path):
        # type: (str, str) -> (str, tuple)
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
        # MULTI_TOKEN name tokens can match the related type 0 to N times.
        # Tokens are ignored from the match length since we favor a match with specific names over another with
        # generic tokens.
        matched_length_by_res = {}
        matched_groups_by_res = {}
        for res_key, res_segments in service_resources.items():
            match_len = 0
            res_regex = r"^"
            for segment in res_segments:
                matched_groups = re.match(NAMED_TOKEN_REGEX, segment["name"])
                if matched_groups:
                    # match any name with specific type 1 time only
                    res_regex += rf"/(?P<{matched_groups.groups()[0]}>{SEGMENT_NAME_REGEX})::{segment['type']}"
                elif segment["name"] == MULTI_TOKEN:
                    # match any name with specific type, 0 or more times
                    # TODO: valider ce regex (pour get le nom complet dans multi_token)
                    res_regex += rf"(?P<multi_token>/{SEGMENT_NAME_REGEX}::{segment['type']})*"
                else:
                    # match name and type exactly
                    res_regex += rf"/{segment['name']}::{segment['type']}"
                    match_len += 1
            res_regex += r"$"

            matched_groups = re.match(res_regex, resource_nametype_path)
            if matched_groups:
                matched_length_by_res[res_key] = match_len
                matched_groups_by_res[res_key] = matched_groups

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
        # type: (List[Dict], Match[str]) -> List[Dict]
        """
        Creates resource data. This data includes the name and type of each segments of
        a full resource path.

        :param target_segments: List containing the name and type info of each segment of the target resource path.
        :param matched_groups:
        """
        res_data = []
        # First add 'named' resource data
        for i, segment in enumerate(target_segments):
            matched_groups = re.match(NAMED_TOKEN_REGEX, segment["name"])
            if matched_groups:
                res_data.append({
                    "resource_name": input_matched_groups.group(matched_groups.groups()[0]),
                    "resource_type": segment["type"]
                })
            elif segment["name"] == MULTI_TOKEN:
                multi_segments = input_matched_groups.group("multi_token")
                for seg in multi_segments.split("/"):
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

    def sync(self, perm_operation, permission, src_resource_tree):
        # type: (Callable[[List[Dict]], None], Permission, List[Dict]) -> None
        """
        Create or delete the same permission on each service sharing the same resource.

        :param perm_operation: Magpie create_permission or delete_permission function
        :param permission: Permission to synchronize with others services
        :param src_resource_tree: Resource tree associated with the permission to synchronize
        """
        resource_nametype_path = ""
        for res in src_resource_tree:
            resource_nametype_path += f"/{res['resource_name']}::{res['resource_type']}"

        src_res_key, src_matched_groups = self._find_matching_res(permission.service_name, resource_nametype_path)

        target_permissions = self.find_permissions_to_sync(src_res_key, src_matched_groups, permission, perm_operation)

        for target_key in target_permissions:
            permissions_data = target_permissions[target_key]["res_path"]
            for perm_name, user, group in target_permissions[target_key]["permissions"]:
                # add permission details to last segment
                permissions_data[-1]["permission"] = perm_name
                permissions_data[-1]["user"] = user
                permissions_data[-1]["group"] = group

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
