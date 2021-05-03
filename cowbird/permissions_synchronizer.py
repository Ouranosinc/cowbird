import copy
from typing import TYPE_CHECKING

from cowbird.config import get_all_configs
from cowbird.services.service_factory import ServiceFactory
from cowbird.utils import get_config_path

if TYPE_CHECKING:
    from typing import Dict, Generator, List, Tuple

    from cowbird.services.impl.magpie import Magpie

    SyncPointServicesType = Dict[str, str]
    SyncPointMappingType = List[Dict[str, List[str]]]


class Permission:
    """
    Define every property required to set a permission in Magpie.
    """

    def __init__(self, service_name, resource_id, resource_full_name, name, access, scope, user=None, group=None):
        self.service_name = service_name
        self.resource_id = resource_id
        self.resource_full_name = resource_full_name
        self.name = name
        self.access = access
        self.scope = scope
        self.user = user
        self.group = group

    def __eq__(self, other):
        return self.service_name == other.service_name and \
            self.resource_id == other.resource_id and \
            self.resource_full_name == other.resource_full_name and \
            self.name == other.name and \
            self.access == other.access and \
            self.scope == other.scope and \
            self.user == other.user and \
            self.group == other.group


class SyncPoint:
    """
    A sync point contain services sharing resources via multiple API.

    It defines how the same resource is defined in
    each service and what are the mapping between permission accesses.
    """

    def __init__(self,
                 services,    # type: SyncPointServicesType
                 mapping,     # type: SyncPointMappingType
                 magpie_inst  # type: Magpie
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
        self.mapping = [{svc: perms for svc, perms in mapping_pt.items() if svc in available_services}
                        for mapping_pt in mapping]
        self.magpie_inst = magpie_inst

    def resource_match(self, permission):
        # type: (Permission) -> bool
        """
        Define if the permission name is covered by this sync point.
        """
        return permission.resource_full_name.startswith(self.services[permission.service_name])

    def find_match(self, permission):
        # type: (Permission) -> Generator[Tuple[str, str], None, None]
        """
        Search and yield for every match a (service, permission name) tuple that is mapped with this permission.
        """
        # check if the permission name is covered by this sync point
        if not self.resource_match(permission):
            return

        # For each permission mapping
        for mapping in self.mapping:
            # Does the current service has some mapped permissions?
            if permission.service_name not in mapping:
                continue
            # Does the current permission access is covered?
            if permission.name not in mapping[permission.service_name]:
                continue
            # This permission is mapped : yields matches
            for svc, mapped_perm_name in mapping.items():
                # Don't synch with itself
                if svc == permission.service_name:
                    continue
                for perm_name in mapped_perm_name:
                    yield svc, perm_name

    def sync(self, operation, permission):
        # type: (str, Permission) -> None
        """
        Create or delete the same permission on each service sharing the same resource.

        @param operation Magpie create_permission or delete_permission function name
        @param permission Permission to synchronize with others services
        """
        res_common_part_idx = len(self.services[permission.service_name])
        for svc, perm_name in self.find_match(permission):
            new_permission = copy.copy(permission)
            new_permission.service_name = svc
            new_permission.resource_full_name = self.services[svc] + \
                permission.resource_full_name[res_common_part_idx:]
            new_permission.resource_id = ServiceFactory().get_service(svc).get_resource_id(
                new_permission.resource_full_name)
            new_permission.name = perm_name
            fct = getattr(self.magpie_inst, operation)
            fct(new_permission)


class PermissionSynchronizer(object):
    """
    Keep service-shared resources in sync when permissions are updated for one of them.

    TODO: At some point we will need a consistency function that goes through all permissions of all services and make
          sure that linked services have the same permissions.
    """

    def __init__(self, magpie_inst):
        config_path = get_config_path()
        sync_perm_cfg = get_all_configs(config_path, "sync_permissions", allow_missing=True)[0]
        self.sync_point = []

        for sync_cfg in sync_perm_cfg.values():
            self.sync_point.append(SyncPoint(services=sync_cfg["services"],
                                             mapping=sync_cfg["permissions_mapping"],
                                             magpie_inst=magpie_inst))

    def create_permission(self, permission):
        # type: (Permission) -> None
        """
        Create the same permission on each service sharing the same resource.
        """
        for point in self.sync_point:
            point.sync("create_permission", permission)

    def delete_permission(self, permission):
        # type: (Permission) -> None
        """
        Delete the same permission on each service sharing the same resource.
        """
        for point in self.sync_point:
            point.sync("delete_permission", permission)
