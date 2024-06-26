from pyramid.config import Configurator

from cowbird.api import schemas as s
from cowbird.utils import get_logger


def includeme(config: Configurator) -> None:
    logger = get_logger(__name__)
    logger.info("Adding API base routes...")
    config.add_route(**s.service_api_route_info(s.HandlersAPI))
    config.add_route(**s.service_api_route_info(s.HandlerAPI))
    config.add_route(**s.service_api_route_info(s.HandlerResyncAPI))
    config.scan()
