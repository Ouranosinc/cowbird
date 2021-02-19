from typing import TYPE_CHECKING
from cowbird.services.impl.catalog import Catalog
from cowbird.services.impl.geoserver import Geoserver
from cowbird.services.impl.magpie import Magpie
from cowbird.services.impl.nginx import Nginx
from cowbird.services.impl.thredds import Thredds

if TYPE_CHECKING:
    from typing import List

    from cowbird.typedefs import AnySettingsContainer


def get_services(container):
    # type: (AnySettingsContainer) -> List[Service]
    """
    Obtains the services managed by the application.
    """
    return [Catalog("Catalog"),
            Geoserver("Geoserver"),
            Magpie("Magpie"),
            Nginx("Nginx"),
            Thredds("Thredds")]