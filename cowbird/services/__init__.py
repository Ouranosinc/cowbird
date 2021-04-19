from typing import TYPE_CHECKING

from cowbird.services.service_factory import ServiceFactory

if TYPE_CHECKING:
    from typing import List

    from cowbird.typedefs import AnySettingsContainer


def get_services(container):
    # type: (AnySettingsContainer) -> List[Service]
    """
    Obtains the services managed by the application.
    """
    return ServiceFactory().get_active_services()
