from cowbird.api import schemas as s
from cowbird.utils import get_logger


def includeme(config):
    logger = get_logger(__name__)
    logger.info("Adding API base routes...")
    config.add_route(**s.service_api_route_info(s.ServicesAPI))
    config.add_route(**s.service_api_route_info(s.ServiceAPI))
    config.scan()
