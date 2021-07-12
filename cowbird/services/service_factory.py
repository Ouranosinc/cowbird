import importlib
from typing import TYPE_CHECKING

import six

from cowbird.config import get_all_configs
from cowbird.utils import SingletonMeta, get_config_path, get_logger

if TYPE_CHECKING:
    from typing import List

    from cowbird.services.service import Service

LOGGER = get_logger(__name__)

VALID_SERVICES = ["Catalog", "Geoserver", "Magpie", "Nginx", "Thredds",
                  "FileSystem"]


@six.add_metaclass(SingletonMeta)
class ServiceFactory:
    """
    Create service instance using service name.
    """

    def __init__(self):
        config_path = get_config_path()
        configs = get_all_configs(config_path, "services", allow_missing=True)
        self.services_cfg = configs[0] if configs else {}
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
                svc = cls(name, self.services_cfg[name].get("url", None))
            self.services[name] = svc
            return svc

    def get_active_services(self):
        # type: (ServiceFactory) -> List[Service]
        """
        Return a list of `Service` implementation activated in the config.
        """
        return list(filter(None, [self.get_service(name) for name in self.services_cfg]))
