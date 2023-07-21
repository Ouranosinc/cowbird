from pyramid.config import Configurator

from cowbird.api import schemas as s
from cowbird.utils import get_logger


def includeme(config: Configurator) -> None:
    logger = get_logger(__name__)
    logger.info("Adding webhooks base routes...")
    config.add_route(**s.service_api_route_info(s.UserWebhookAPI))
    config.add_route(**s.service_api_route_info(s.PermissionWebhookAPI))
    config.scan()
