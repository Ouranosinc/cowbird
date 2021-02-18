from pyramid.security import NO_PERMISSION_REQUIRED

from cowbird.api import schemas as s
from cowbird.api.swagger.views import api_schema, api_swagger
from cowbird.utils import get_logger


def includeme(config):
    logger = get_logger(__name__)
    logger.info("Adding swagger...")
    config.add_route(**s.service_api_route_info(s.SwaggerAPI))
    config.add_route(**s.service_api_route_info(s.SwaggerGenerator))
    config.add_view(api_schema, route_name=s.SwaggerGenerator.name, request_method="GET",
                    renderer="json", permission=NO_PERMISSION_REQUIRED)
    config.add_view(api_swagger, route_name=s.SwaggerAPI.name,
                    renderer="templates/swagger_ui.mako", permission=NO_PERMISSION_REQUIRED)
