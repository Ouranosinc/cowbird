import copy
import re
from typing import TYPE_CHECKING

from cowbird.config import get_all_configs, validate_sync_config
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
                 services,    # type: SyncPointServicesType
                 mapping      # type: SyncPointMappingType
                 ):           # type: (...) -> None
        """
        Init the sync point, holding services with their respective resources root and how access are mapped between
        them.

        @param services: Dict, where the service is the key and its resources root is the value
        @param mapping: List of dict where the service is the key and an access list is the value
        """
        available_services = ServiceFactory().services_cfg.keys()
        # Make sure that only active services are used
        self.services = {svc: svc_cfg for svc, svc_cfg in services.items() if svc in available_services}
        self.resource_roots = {res_key: res for svc in self.services.values() for res_key, res in svc.items()}
        self.mapping = [{res_key: perms for res_key, perms in mapping_pt.items() if res_key in self.resource_roots.keys()}
                        for mapping_pt in mapping]

    def find_match(self, permission, res_root_key):
        # type: (Permission, String) -> Generator[Tuple[str, str], None, None]
        """
        Search and yield for every match a (service, permission name) tuple that is mapped with this permission.
        """
        # For each permission mapping
        for mapping in self.mapping:
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

    def sync(self, perm_operation, permission, src_resource_tree):
        # type: (Callable[[List[Dict]], None], Permission, List[Dict]) -> None
        """
        Create or delete the same permission on each service sharing the same resource.

        @param perm_operation Magpie create_permission or delete_permission function
        @param permission Permission to synchronize with others services
        @param src_resource_tree Resource tree associated with the permission to synchronize
        """
        service_resources = self.services[permission.service_name]
        resource_full_name_type = ""
        for res in src_resource_tree:
            resource_full_name_type += f"/{res['resource_name']}:{res['resource_type']}"

        # Find which resource from the config matches with the input permission's resource tree
        # The length of a match is determined by the number of named segments matching the input resource.
        # `**` name tokens can match the related type 0 to N times. They are ignored from the match length since it is
        # ambiguous in the case of a 0 length match.
        # `*` name tokens can match exactly 1 time only. They are ignored from the match length since we favor a match
        # with specific names over another with `*` generic tokens.
        matched_res_dict = {}
        for res_key, res_segments in service_resources.items():
            match_len = 0
            res_regex = "^"
            for i in range(len(res_segments)):
                if res_segments[i]["name"] == "*":
                    # match any name with specific type 1 time only
                    res_regex += rf"/\w+:{res_segments[i]['type']}"
                elif res_segments[i]["name"] == "**":
                    # match any name with specific type, 0 or more times
                    res_regex += rf"(/\w+:{res_segments[i]['type']})*"
                else:
                    # match name and type exactly
                    res_regex += f"/{res_segments[i]['name']:}:{res_segments[i]['type']}"
                    match_len += 1
            res_regex += "$"
            if re.match(res_regex, resource_full_name_type):
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

        src_common_part_idx = matched_res_dict[src_res_key]
        for new_res_key, perm_name in self.find_match(permission, src_res_key):
            # Find which service is associated with the new permission
            svc_list = [s for s in self.services if new_res_key in self.services[s]]
            # Assume the service is the first found with the resource key, since the resource keys should be unique.
            svc_name = svc_list[0]
            svc = ServiceFactory().get_service(svc_name)
            if not svc:
                raise ValueError("Invalid service found in the permission mappings. Check if the config.yml file is "
                                 "configured correctly, and if all services found in permissions_mapping are active"
                                 "and have valid service names.")

            target_res = self.services[svc_name][new_res_key]
            permissions_data = []
            suffix_target_res = []
            for i in range(len(target_res)):
                if target_res[i]["name"] in ["*", "**"]:
                    suffix_target_res = target_res[i:]
                    break
                else:
                    permissions_data.append({
                        "resource_name": target_res[i]["name"],
                        "resource_type": target_res[i]["type"]
                    })
            if suffix_target_res:
                suffix_regex = "^"
                for i in range(len(suffix_target_res)):
                    if suffix_target_res[i]["name"] == "*":
                        # match 1 name only
                        suffix_regex += r"(/\w+)"
                    elif suffix_target_res[i]["name"] == "**":
                        # match any name 0 or more times
                        suffix_regex += rf"((?:/\w+)*)"
                suffix_regex += "$"

                src_common_parts = ""
                for res in src_resource_tree[src_common_part_idx:]:
                    src_common_parts += f"/{res['resource_name']}"
                matched_groups = re.match(suffix_regex, src_common_parts)
                if matched_groups:
                    if len(matched_groups.groups()) != len(suffix_target_res):
                        raise RuntimeError(f"Number of matched groups {matched_groups} do not correspond with the"
                                           f"number of suffix config resource {suffix_target_res}.")
                    for i in range(len(suffix_target_res)):
                        match = matched_groups.groups()[i]
                        for segment in match.split("/"):
                            # ignore empty matches which can happen with multitokens with zero occurence
                            if segment:
                                permissions_data.append({
                                    "resource_name": segment,
                                    "resource_type": suffix_target_res[i]["type"]
                                })
                else:
                    raise ValueError(f"Config mismatch between remaining resource_path {src_common_parts} "
                                     "and tokenized target segments.")

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
                                                 mapping=sync_cfg["permissions_mapping"]))

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
