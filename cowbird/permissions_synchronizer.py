import re
from typing import TYPE_CHECKING

from cowbird.config import MULTI_TOKEN, SINGLE_TOKEN, get_all_configs, validate_sync_config
from cowbird.services.service_factory import ServiceFactory
from cowbird.utils import get_config_path, get_logger

if TYPE_CHECKING:
    from typing import Callable, Dict, Generator, List, Tuple

    from cowbird.services.impl.magpie import Magpie

    SyncPointServicesType = Dict[str, str]
    SyncPointMappingType = List[Dict[str, List[str]]]

LOGGER = get_logger(__name__)


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
        self.resource_keys = {res_key: res for svc in self.services.values() for res_key, res in svc.items()}
        self.permissions_mapping = [{res_key: perms for res_key, perms in permissions_mapping.items()
                                    if res_key in self.resource_keys.keys()}
                                    for permissions_mapping in permissions_mapping_list]

    def find_permissions_to_sync(self, permission, res_root_key):
        # type: (Permission, str) -> Generator[Tuple[str, str], None, None]
        """
        Search and yield for every match a (service, permission name) tuple that is mapped with this permission.
        """
        # For each permission mapping
        for mapping in self.permissions_mapping:
            # Does the current service has some mapped permissions?
            if res_root_key not in mapping:
                continue
            # Does the current permission access is covered?
            if permission.name not in mapping[res_root_key]:
                continue
            # This permission is mapped : yields matches
            for res, mapped_perm_name in mapping.items():
                # Don't synch with itself
                if res == res_root_key:
                    continue
                for perm_name in mapped_perm_name:
                    yield res, perm_name

    def _find_matching_res(self, service_name, resource_nametype_path):
        # type: (str, str) -> (str, int)
        """
        Finds a resource key that matches the input resource path, in the sync_permissions config.
        Note that it returns the longest match and only the named segments of the path are included in the length value.
        Any tokenized segment is ignored in the length.

        :param service_name: Name of the service associated with the input resource.
        :param resource_nametype_path: Full resource path name, which includes the type of each segment
                                       (ex.: /name1:type1/name2:type2)
        """
        service_resources = self.services[service_name]
        # Find which resource from the config matches with the input permission's resource tree
        # The length of a match is determined by the number of named segments matching the input resource.
        # MULTI_TOKEN name tokens can match the related type 0 to N times. They are ignored from the match length since
        # it is ambiguous in the case of a 0 length match.
        # SINGLE_TOKEN name tokens can match exactly 1 time only. They are ignored from the match length since we favor
        # a match with specific names over another with SINGLE_TOKEN generic tokens.
        matched_res_dict = {}
        for res_key, res_segments in service_resources.items():
            match_len = 0
            res_regex = "^"
            for segment in res_segments:
                if segment["name"] == SINGLE_TOKEN:
                    # match any name with specific type 1 time only
                    res_regex += rf"/\w+:{segment['type']}"
                elif segment["name"] == MULTI_TOKEN:
                    # match any name with specific type, 0 or more times
                    res_regex += rf"(/\w+:{segment['type']})*"
                else:
                    # match name and type exactly
                    res_regex += f"/{segment['name']:}:{segment['type']}"
                    match_len += 1
            res_regex += "$"
            if re.match(res_regex, resource_nametype_path):
                matched_res_dict[res_key] = match_len

        # Find the longest match
        max_matching_keys = [res for res, match_len in matched_res_dict.items()
                             if match_len == max(matched_res_dict.values())]
        if len(max_matching_keys) == 1:
            src_res_key = max_matching_keys[0]
        elif len(max_matching_keys) > 1:
            raise ValueError("Found 2 matching resources of the same length in the config. Ambiguous config resources :"
                             f" {max_matching_keys}")
        else:
            raise ValueError("No matching resources could be found in the config file.")
        return src_res_key, matched_res_dict[src_res_key]

    @staticmethod
    def _create_res_data(target_segments, src_resource_suffix):
        # type: (List[Dict], List[Dict]) -> List[Dict]
        """
        Creates resource data used to update permissions. This data includes the name and type of each segments of
        a full resource path.

        :param target_segments: List containing the name and type info of each segment of the target resource path.
        :param src_resource_suffix: List similar to the `target_res` argument, but for the input source resource. This
                                   list contains only the suffix section of the resource path, which is the part that is
                                   common to both source and target resource paths.
        """
        permissions_data = []
        suffix_target_segments = []
        # First add 'named' resource data
        for i, segment in enumerate(target_segments):
            if segment["name"] in [SINGLE_TOKEN, MULTI_TOKEN]:  # pylint: disable=no-else-break
                suffix_target_segments = target_segments[i:]
                break
            else:
                permissions_data.append({
                    "resource_name": segment["name"],
                    "resource_type": segment["type"]
                })
        # Then add 'tokenenized' resource data, if any
        if suffix_target_segments:
            # Make regex for the tokenized part of the target resource
            suffix_regex = "^"
            for segment in suffix_target_segments:
                if segment["name"] == SINGLE_TOKEN:
                    # match 1 name only
                    suffix_regex += r"(/\w+)"
                elif segment["name"] == MULTI_TOKEN:
                    # match any name 0 or more times
                    suffix_regex += r"((?:/\w+)*)"
            suffix_regex += "$"

            # Check if the source suffix matches the target regex
            src_common_parts = ""
            for res in src_resource_suffix:
                src_common_parts += f"/{res['resource_name']}"
            matched_groups = re.match(suffix_regex, src_common_parts)
            if matched_groups:
                if len(matched_groups.groups()) != len(suffix_target_segments):
                    raise RuntimeError(f"Number of matched groups {matched_groups} do not correspond with the"
                                       f"number of suffix config resource {suffix_target_segments}.")

                # Add each tokenized segment to the resulting data
                for i, suffix_segment in enumerate(suffix_target_segments):
                    match = matched_groups.groups()[i]
                    # Loop on each segment of a match, since a multi_token can produce multiple segment in a match.
                    for match_segment in match.split("/"):
                        # ignore empty matches which can happen with multitokens with zero occurence
                        if match_segment:
                            permissions_data.append({
                                "resource_name": match_segment,
                                "resource_type": suffix_segment["type"]
                            })
            else:
                raise ValueError(f"Config mismatch between remaining resource_path {src_common_parts} "
                                 "and tokenized target segments.")
        return permissions_data

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
            resource_nametype_path += f"/{res['resource_name']}:{res['resource_type']}"

        src_res_key, src_suffix_idx = self._find_matching_res(permission.service_name, resource_nametype_path)

        for new_res_key, perm_name in self.find_permissions_to_sync(permission, src_res_key):
            # Find which service is associated with the new permission, and check if it is valid
            svc_list = [s for s in self.services if new_res_key in self.services[s]]
            # Assume the service is the first found with the resource key, since the resource keys should be unique.
            svc_name = svc_list[0]
            svc = ServiceFactory().get_service(svc_name)
            if not svc:
                raise ValueError("Invalid service found in the permission mappings. Check if the config.yml file is "
                                 "configured correctly, and if all services found in permissions_mapping are active"
                                 "and have valid service names.")

            target_segments = self.services[svc_name][new_res_key]
            permissions_data = SyncPoint._create_res_data(target_segments, src_resource_tree[src_suffix_idx:])

            # add permission details to last segment
            permissions_data[-1]["permission"] = perm_name
            permissions_data[-1]["user"] = permission.user
            permissions_data[-1]["group"] = permission.group

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
