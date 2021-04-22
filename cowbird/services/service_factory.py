from typing import TYPE_CHECKING

import six

from cowbird.config import get_all_configs
from cowbird.utils import SingletonMeta, get_config_path

if TYPE_CHECKING:
    from typing import List

    from cowbird.services.service import Service

VALID_SERVICES = ["Catalog", "Geoserver", "Magpie", "Nginx", "Thredds",
                  "FileSystem"]


@six.add_metaclass(SingletonMeta)
class ServiceFactory:
    """
    Create service instance using service name.
    """

    def __init__(self):
        config_path = get_config_path()
        self.services_cfg = get_all_configs(config_path, "services", allow_missing=True)[0]
        self.services = {}

    def get_service(self, name):
        # type: (ServiceFactory, str) -> Service
        """
        Instantiates a `Service` implementation using its name if it doesn't exist or else returns the existing one from
        cache.
        """
        try:
            return self.services[name]
        except KeyError:
            # pylint: disable=W0641,unused-import
            from cowbird.services.impl.catalog import Catalog  # noqa: F401
            from cowbird.services.impl.filesystem import FileSystem  # noqa: F401
            from cowbird.services.impl.geoserver import Geoserver  # noqa: F401
            from cowbird.services.impl.magpie import Magpie  # noqa: F401
            from cowbird.services.impl.nginx import Nginx  # noqa: F401
            from cowbird.services.impl.thredds import Thredds  # noqa: F401

            svc = None
            if name in VALID_SERVICES and \
               name in self.services_cfg and \
               self.services_cfg[name].get("active", False):
                cls = locals()[name]
                svc = cls(name, self.services_cfg[name].get("url", None))
            self.services[name] = svc
            return svc

    def get_active_services(self):
        # type: (ServiceFactory) -> List[Service]
        """
        Return a list of `Service` implementation activated in the config.
        """
        return list(filter(None, [self.get_service(name) for name in self.services_cfg]))
