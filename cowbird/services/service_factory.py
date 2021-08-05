import importlib
from typing import TYPE_CHECKING

from cowbird.config import get_all_configs
from cowbird.utils import SingletonMeta, get_config_path, get_logger

if TYPE_CHECKING:
    from typing import List

    from cowbird.services.service import Service

LOGGER = get_logger(__name__)

VALID_SERVICES = ["Catalog", "Geoserver", "Magpie", "Nginx", "Thredds",
                  "FileSystem"]


class ServiceFactory(metaclass=SingletonMeta):
    """
    Create service instance using service name.
    """

    def __init__(self):
        config_path = get_config_path()
        svcs_configs = get_all_configs(config_path, "services", allow_missing=True)
        self.services_cfg = {}
        for svcs_config in svcs_configs:
            if not svcs_config:
                LOGGER.warning("Services configuration is empty.")
                continue
            for name, cfg in svcs_config.items():
                if name in self.services_cfg:
                    LOGGER.warning("Ignoring a duplicate service configuration for [%s].", name)
                else:
                    self.services_cfg[name] = cfg
        self.services = {}
        LOGGER.info("Services config : [%s]", ", ".join(["{0} [{1}]".format(name, cfg.get("active", False))
                                                         for name, cfg in self.services_cfg.items()]))

    def get_service(self, name):
        # type: (ServiceFactory, str) -> Service
        """
        Instantiates a `Service` implementation using its name if it doesn't exist or else returns the existing one from
        cache.
        """
        try:
            return self.services[name]
        except KeyError:
            svc = None
            if name in VALID_SERVICES and \
               name in self.services_cfg and \
               self.services_cfg[name].get("active", False):
                module = importlib.import_module(".".join(["cowbird.services.impl", name.lower()]))
                cls = getattr(module, name)
                svc = cls(name, **self.services_cfg[name])
            self.services[name] = svc
            return svc

    def get_active_services(self):
        # type: (ServiceFactory) -> List[Service]
        """
        Return a sorted list by priority of `Service` implementation activated in the config.
        """
        return sorted(filter(None, [self.get_service(name) for name in self.services_cfg]),
                      key=lambda svc: svc.priority)
