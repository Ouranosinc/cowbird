from typing import TYPE_CHECKING

import six

from cowbird.config import get_all_configs
from cowbird.utils import get_config_path

if TYPE_CHECKING:
    from typing import Dict, Generator, List, Tuple

    if six.PY2:
        # pylint: disable=E0602,undefined-variable  # unicode not recognized by python 3
        Str = Union[AnyStr, unicode]  # noqa: E0602,F405,F821
    else:
        Str = str

    SyncPointServicesType = Dict[Str, Str]
    SyncPointMappingType = List[Dict[Str, List[Str]]]


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

    def get_resource_name(self):
        # FIXME: Needs to convert resource id to full hierarchy name
        return self.resource_id


class SyncPoint:
    """
    A sync point contain services sharing resources via multiple API.

    It defines how the same resource is defined in
    each service and what are the mapping between permission accesses.
    """

    def __init__(self,
                 services,  # type: SyncPointServicesType
                 mapping    # type: SyncPointMappingType
                 ):         # type: (...) -> None
        """
        Init the sync point, holding services with their respective resources root and how access are mapped between
        them.

        @param services: Dict, where the service is the key and its resources root is the value
        @param mapping: List of dict where the service is the key and an access list is the value
        """
        self.services = services
        self.mapping = mapping

    def resource_match(self, permission):
        # type: (Permission) -> bool
        """
        Define if the permission name is covered by this sync point.
        """
        # FIXME: Must handle regex or only take root part of resource name in config
        return permission.name.startswith(self.services[permission.service_name])

    def resource_common_part(self, permission):
        # type: (Permission) -> str
        """
        Return the part of the resource name being shared between services.
        """
        # FIXME: Must handle regex or only take root part of resource name in config
        return permission.resource_full_name.strip(self.services[permission.service_name])

    def find_match(self, permission):
        # type: (Permission) -> Generator[Tuple[Str, Str], None, None]
        """
        Search and yield for every service, access tuple that is mapped with this permission.
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
            if permission.access not in mapping[permission.service_name]:
                continue
            # This permission is mapped : yields matches
            for svc, mapped_perm in mapping.items():
                # Don't synch with itself
                if svc == permission.service_name:
                    continue
                for perm in mapped_perm:
                    yield svc, perm

    def create(self, permission):
        # type: (Permission) -> None
        """
        Create the same permission on each service sharing the same resource.
        """
        perm_common_part = self.resource_common_part(permission)
        for svc, perm in self.find_match(permission):
            # FIXME: Must handle regex or only take root part of resource name in config
            full_perm_name = self.services[svc] + perm_common_part
            # TODO: Call Magpie to set this permission on `svc` using `full_perm_name`
            print(perm)
            print(full_perm_name)

    def delete(self, permission):
        # type: (Permission) -> None
        """
        Remove the same permission on each service sharing the same resource.
        """
        perm_common_part = self.resource_common_part(permission)
        for svc, perm in self.find_match(permission):
            # FIXME: Must handle regex or only take root part of resource name in config
            full_perm_name = self.services[svc] + perm_common_part
            # TODO: Call Magpie to remove this permission on `svc` using `full_perm_name`
            print(perm)
            print(full_perm_name)


class PermissionSynchronizer(object):
    """
    Keep service-shared resources in sync when permissions are updated for one of them.

    TODO: At some point we will need a consistency function that goes through all permissions of all services and make
          sure that linked services have the same permissions.
    """

    def __init__(self):
        config_path = get_config_path()
        sync_perm_cfg = get_all_configs(config_path, "sync_permissions", allow_missing=True)[0]
        self.sync_point = []
        for sync_cfg in sync_perm_cfg.values():
            self.sync_point.append(SyncPoint(services=sync_cfg[0]["service"][0],
                                             mapping=sync_cfg[0]["permissions_mapping"]))

    def create_permission(self, permission):
        # type: (Permission) -> None
        """
        Create the same permission on each service sharing the same resource.
        """
        for point in self.sync_point:
            point.create(permission)

    def delete_permission(self, permission):
        # type: (Permission) -> None
        """
        Delete the same permission on each service sharing the same resource.
        """
        for point in self.sync_point:
            point.delete(permission)
