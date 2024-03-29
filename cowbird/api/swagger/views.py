import os

from pyramid.request import Request

from cowbird.api import schemas as s
from cowbird.constants import get_constant
from cowbird.typedefs import JSON


@s.SwaggerAPI.get(tags=[s.APITag], response_schemas=s.SwaggerAPI_GET_responses)
def api_swagger(request: Request) -> JSON:  # noqa: F811
    """
    Swagger UI route to display the Cowbird REST API schemas.
    """
    cowbird_module: str = get_constant("COWBIRD_MODULE_DIR")
    swagger_versions_dir = os.path.abspath(os.path.join(cowbird_module, "ui/swagger/versions"))
    swagger_ui_path = s.SwaggerGenerator.path.lstrip("/")
    return_data: JSON = {
        "api_title": s.TitleAPI,
        "api_schema_path": swagger_ui_path,
        "api_schema_versions_dir": swagger_versions_dir,
    }
    return return_data


@s.SwaggerGenerator.get(tags=[s.APITag], response_schemas=s.SwaggerAPI_GET_responses)
def api_schema(request: Request) -> JSON:
    """
    Return JSON Swagger specifications of Cowbird REST API.
    """
    swagger_base_spec: JSON = {
        "host": get_constant("COWBIRD_URL", request),
        "schemes": [request.scheme]
    }
    return s.generate_api_schema(swagger_base_spec)
