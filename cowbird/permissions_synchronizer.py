from cowbird.config import get_all_configs
from cowbird.utils import get_constant, get_settings


class PermissionSynchronizer(object):
    """
    Keep service-shared resources in synch when permissions are updated for one of them.

    synch_permissions:
    user_workspace:
      services:
        geoserver: /api/workspaces/private/*
        thredds: /catalog/birdhouse/workspaces/private/*
      permissions_mapping:
        - geoserver:
            - read
          thredds:
            - read
            - browse
        - geoserver:
            - write
          thredds:
            - execute
    """

    def __init__(self):
        settings = get_settings(None, app=True)
        config_path = get_constant("COWBIRD_CONFIG_PATH", settings,
                                   default_value=None,
                                   raise_missing=False, raise_not_set=False,
                                   print_missing=True)
        get_all_configs(config_path, "synch_permissions",
                        allow_missing=True)
        # TODO: Matrix to speard permissions accross services

    def set_permission(self, permission):
        # TODO:
        pass

    def delete_permission(self, permission):
        # TODO:
        pass
