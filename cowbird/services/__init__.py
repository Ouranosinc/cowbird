from typing import TYPE_CHECKING
from cowbird.services.impl.catalog import Catalog
from cowbird.services.impl.geoserver import Geoserver
from cowbird.services.impl.magpie import Magpie
from cowbird.services.impl.nginx import Nginx
from cowbird.services.impl.thredds import Thredds
from cowbird.services.impl.filesystem import FileSystem
from cowbird.services.service import Service
from cowbird.constants import get_constant
from cowbird.config import get_all_configs
from cowbird.utils import get_settings
if TYPE_CHECKING:
    from typing import List

    from cowbird.typedefs import AnySettingsContainer

VALID_SERVICES = ["Catalog", "Geoserver", "Magpie", "Nginx", "Thredds",
                  "FileSystem"]


def get_services(container):
    # type: (AnySettingsContainer) -> List[Service]
    """
    Obtains the services managed by the application.
    """
    settings = get_settings(container, app=True)
    config_path = get_constant("COWBIRD_CONFIG_PATH", settings,
                               default_value=None,
                               raise_missing=False, raise_not_set=False,
                               print_missing=True)
    components_cfg = get_all_configs(config_path, "components",
                                     allow_missing=True)
    components = []
    for c, desc in components_cfg[0].items():
        if desc['active'] and c in VALID_SERVICES:
            cls = globals()[c]
            components.append(cls(c, desc.get('url', None)))
    return components
