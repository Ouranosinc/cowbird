from pyramid.config import Configurator

from cowbird.api import schemas as s
from cowbird.utils import get_logger

LOGGER = get_logger(__name__)


def includeme(config: Configurator) -> None:
    LOGGER.info("Adding API base routes...")
    config.add_route(**s.service_api_route_info(s.VersionAPI))
    config.add_route(**s.service_api_route_info(s.HomepageAPI))
    config.scan()
