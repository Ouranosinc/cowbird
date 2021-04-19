import six

from cowbird.config import get_all_configs
from cowbird.constants import get_constant
from cowbird.services.impl.catalog import Catalog  # noqa: F401
from cowbird.services.impl.filesystem import FileSystem  # noqa: F401
from cowbird.services.impl.geoserver import Geoserver  # noqa: F401
from cowbird.services.impl.magpie import Magpie  # noqa: F401
from cowbird.services.impl.nginx import Nginx  # noqa: F401
from cowbird.services.impl.thredds import Thredds  # noqa: F401
from cowbird.utils import get_settings
from cowbird.utils import SingletonMeta


VALID_SERVICES = ["Catalog", "Geoserver", "Magpie", "Nginx", "Thredds",
                  "FileSystem"]


@six.add_metaclass(SingletonMeta)
class ServiceFactory:
    """
    Create service instance using service name
    """
    def __init__(self):
        settings = get_settings(None, app=True)
        config_path = get_constant("COWBIRD_CONFIG_PATH", settings,
                                   default_value=None,
                                   raise_missing=False, raise_not_set=False,
                                   print_missing=True)
        self.services_cfg = get_all_configs(config_path, "services", allow_missing=True)[0]
        self.services = {}

    def get_service(self, name):
        # type: (str) -> Service
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
                cls = globals()[name]
                svc = cls(name, self.services_cfg[name].get("url", None))
            self.services[name] = svc
            return svc

    def get_active_services(self):
        # type: (None) -> List[Service]
        """
        Return a list of `Service` implementation activated in the config.
        """
        return list(filter(None, [self.get_service(name) for name in self.services_cfg]))
