from typing import TYPE_CHECKING

import colander
from cornice import Service
from cornice.service import get_services
from cornice_swagger.swagger import CorniceSwagger
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPMethodNotAllowed,
    HTTPNotAcceptable,
    HTTPNotFound,
    HTTPOk,
    HTTPUnauthorized,
    HTTPUnprocessableEntity
)
from pyramid.security import NO_PERMISSION_REQUIRED

from cowbird import __meta__
from cowbird.constants import get_constant
from cowbird.utils import (
    CONTENT_TYPE_HTML,
    CONTENT_TYPE_JSON,
    KNOWN_CONTENT_TYPES,
    SUPPORTED_ACCEPT_TYPES,
    SUPPORTED_FORMAT_TYPES,
    ExtendedEnum
)

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from typing import Dict, List, Union

    from cowbird.typedefs import JSON

# ignore naming style of tags
# pylint: disable=C0103,invalid-name

TitleAPI = f"{__meta__.__title__} REST API"
InfoAPI = {
    "description": __meta__.__description__,
    "contact": {"name": __meta__.__maintainer__, "email": __meta__.__email__, "url": __meta__.__url__}
}


# Security
SecurityCookieAuthAPI = {}  # {"cookieAuth": {"type": "apiKey", "in": "cookie", "name": "token"}}
SecurityDefinitionsAPI = {"securityDefinitions": SecurityCookieAuthAPI}
SecurityAuthenticatedAPI = [{"cookieAuth": []}]
SecurityAdministratorAPI = [{"cookieAuth": []}]
SecurityEveryoneAPI = [{}]


def get_security(service, method):
    definitions = service.definitions
    args = {}
    for definition in definitions:
        met, _, args = definition
        if met == method:
            break
    # automatically retrieve permission if specified within the view definition
    permission = args.get("permission")
    if permission == NO_PERMISSION_REQUIRED:
        return SecurityEveryoneAPI
    if permission == get_constant("COWBIRD_ADMIN_PERMISSION"):
        return SecurityAdministratorAPI
    # return default admin permission otherwise unless specified form cornice decorator
    return SecurityAdministratorAPI if "security" not in args else args["security"]


def service_api_route_info(service_api, **kwargs):
    """
    Employed to simplify Pyramid route and view config definitions from same schema objects.
    """
    kwargs.update({
        "name": service_api.name,
        "pattern": service_api.path,
    })
    kwargs.setdefault("traverse", getattr(service_api, "traverse", None))
    kwargs.setdefault("factory", getattr(service_api, "factory", None))
    return kwargs


class ValidOperations(ExtendedEnum):
    """
    Valid values as webhook event.
    """
    CreateOperation = "created"
    DeleteOperation = "deleted"


def generate_api_schema(swagger_base_spec):
    # type: (Dict[str, Union[str, List[str]]]) -> JSON
    """
    Return JSON Swagger specifications of Cowbird REST API.

    Uses Cornice Services and Schemas to return swagger specification.

    :param swagger_base_spec: dictionary that specifies the 'host' and list of HTTP 'schemes' to employ.
    """
    generator = CorniceSwagger(get_services())
    # function docstrings are used to create the route's summary in Swagger-UI
    generator.summary_docstrings = True
    generator.default_security = get_security
    swagger_base_spec.update(SecurityDefinitionsAPI)
    generator.swagger = swagger_base_spec
    json_api_spec = generator.generate(title=TitleAPI, version=__meta__.__version__, info=InfoAPI)
    for tag in json_api_spec["tags"]:
        tag["description"] = TAG_DESCRIPTIONS[tag["name"]]
    return json_api_spec


# Service Routes

SwaggerGenerator = Service(
    path="/json",
    name="swagger_schema_json")
SwaggerAPI = Service(
    path="/api",
    name="swagger_schema_ui",
    description=f"{TitleAPI} documentation")
VersionAPI = Service(
    path="/version",
    name="Version")
HomepageAPI = Service(
    path="/",
    name="homepage")
ServicesAPI = Service(
    path="/services",
    name="service_list")
ServiceAPI = Service(
    path="/services/{service_name}",
    name="service_detail")
UserWebhookAPI = Service(
    path="/webhooks/users",
    name="user_webhook")
PermissionWebhookAPI = Service(
    path="/webhooks/permissions",
    name="permission_webhook")

# Path parameters
OperationParameter = colander.SchemaNode(
    colander.String(),
    description="Operation to interact with.",
    example="users",)
ServiceNameParameter = colander.SchemaNode(
    colander.String(),
    description="Registered service name.",
    example="my-wps")


class Service_RequestPathSchema(colander.MappingSchema):
    service_name = ServiceNameParameter


# Tags
APITag = "API"
WebhooksTag = "Webhooks"
ServicesTag = "Service"

TAG_DESCRIPTIONS = {
    APITag: "General information about the API.",
    WebhooksTag:
        f"Webhooks that are managed by {__meta__.__title__}.\n\n" +
        "Each of the managed webhook provides specific functionalities against specific services of the stack.",
    ServicesTag:
        f"Services that are managed by {__meta__.__title__}.\n\n" +
        "Each service defines information such as endpoint and configuration details for running webhooks.",
}

# Header definitions


class AcceptType(colander.SchemaNode):
    schema_type = colander.String
    default = CONTENT_TYPE_JSON
    example = CONTENT_TYPE_JSON
    missing = colander.drop


class ContentType(colander.SchemaNode):
    schema_type = colander.String
    name = "Content-Type"
    default = CONTENT_TYPE_JSON
    example = CONTENT_TYPE_JSON
    missing = colander.drop


class RequestHeaderSchemaAPI(colander.MappingSchema):
    accept = AcceptType(name="Accept", validator=colander.OneOf(SUPPORTED_ACCEPT_TYPES),
                        description="Desired MIME type for the response body content.")
    content_type = ContentType(validator=colander.OneOf(KNOWN_CONTENT_TYPES),
                               description="MIME content type of the request body.")


class RequestHeaderSchemaUI(colander.MappingSchema):
    content_type = ContentType(default=CONTENT_TYPE_HTML, example=CONTENT_TYPE_HTML,
                               description="MIME content type of the request body.")


class QueryRequestSchemaAPI(colander.MappingSchema):
    format = AcceptType(validator=colander.OneOf(SUPPORTED_FORMAT_TYPES),
                        description="Desired MIME type for the response body content. "
                                    "This formatting alternative by query parameter overrides the Accept header.")


class BaseRequestSchemaAPI(colander.MappingSchema):
    header = RequestHeaderSchemaAPI()
    querystring = QueryRequestSchemaAPI()


class HeaderResponseSchema(colander.MappingSchema):
    content_type = ContentType(validator=colander.OneOf(SUPPORTED_ACCEPT_TYPES),
                               description="MIME content type of the response body.")


class BaseResponseSchemaAPI(colander.MappingSchema):
    header = HeaderResponseSchema()


class BaseResponseBodySchema(colander.MappingSchema):
    def __init__(self, code, description, **kw):
        super(BaseResponseBodySchema, self).__init__(**kw)
        assert isinstance(code, int)         # nosec: B101
        assert isinstance(description, str)  # nosec: B101
        self.__code = code  # pylint: disable=W0238,unused-private-member
        self.__desc = description  # pylint: disable=W0238,unused-private-member

        # update the values
        child_nodes = getattr(self, "children", [])
        child_nodes.append(colander.SchemaNode(
            colander.Integer(),
            name="code",
            description="HTTP response code",
            example=code))
        child_nodes.append(colander.SchemaNode(
            colander.String(),
            name="type",
            description="Response content type",
            example=CONTENT_TYPE_JSON))
        child_nodes.append(colander.SchemaNode(
            colander.String(),
            name="detail",
            description="Response status message",
            example=description))


class ErrorVerifyParamConditions(colander.MappingSchema):
    not_none = colander.SchemaNode(colander.Boolean(), missing=colander.drop)
    not_empty = colander.SchemaNode(colander.Boolean(), missing=colander.drop)
    not_in = colander.SchemaNode(colander.Boolean(), missing=colander.drop)
    not_equal = colander.SchemaNode(colander.Boolean(), missing=colander.drop)
    is_none = colander.SchemaNode(colander.Boolean(), missing=colander.drop)
    is_empty = colander.SchemaNode(colander.Boolean(), missing=colander.drop)
    is_in = colander.SchemaNode(colander.Boolean(), missing=colander.drop)
    is_equal = colander.SchemaNode(colander.Boolean(), missing=colander.drop)
    is_true = colander.SchemaNode(colander.Boolean(), missing=colander.drop)
    is_false = colander.SchemaNode(colander.Boolean(), missing=colander.drop)
    is_type = colander.SchemaNode(colander.Boolean(), missing=colander.drop)
    matches = colander.SchemaNode(colander.Boolean(), missing=colander.drop)


class ErrorVerifyParamBodySchema(colander.MappingSchema):
    name = colander.SchemaNode(
        colander.String(),
        description="Name of the failing condition parameter that caused the error.",
        missing=colander.drop)
    value = colander.SchemaNode(
        colander.String(),
        description="Value of the failing condition parameter that caused the error.",
        default=None)
    compare = colander.SchemaNode(
        colander.String(),
        description="Comparison value(s) employed for evaluation of the failing condition parameter.",
        missing=colander.drop)
    conditions = ErrorVerifyParamConditions(
        description="Evaluated conditions on the parameter value with corresponding validation status. "
                    "Some results are relative to the comparison value when provided.")


class ErrorFallbackBodySchema(colander.MappingSchema):
    exception = colander.SchemaNode(colander.String(), description="Raise exception.")
    error = colander.SchemaNode(colander.String(), description="Error message describing the cause of exception.")


class ErrorCallBodySchema(ErrorFallbackBodySchema):
    detail = colander.SchemaNode(colander.String(), description="Contextual explanation about the cause of error.")
    content = colander.MappingSchema(default=None, unknown="preserve",
                                     description="Additional contextual details that lead to the error. "
                                                 "Can have any amount of sub-field to describe evaluated values.")


class ErrorResponseBodySchema(BaseResponseBodySchema):
    def __init__(self, code, description, **kw):
        super(ErrorResponseBodySchema, self).__init__(code, description, **kw)
        assert code >= 400  # nosec: B101

    route_name = colander.SchemaNode(
        colander.String(),
        description="Route called that generated the error.",
        example="/users/toto")
    request_url = colander.SchemaNode(
        colander.String(),
        title="Request URL",
        description="Request URL that generated the error.",
        example="http://localhost:2001/cowbird/users/toto")
    method = colander.SchemaNode(
        colander.String(),
        description="Request method that generated the error.",
        example="GET")
    param = ErrorVerifyParamBodySchema(
        title="Parameter",
        missing=colander.drop,
        description="Additional parameter details to explain the cause of error.")
    call = ErrorCallBodySchema(
        missing=colander.drop,
        description="Additional details to explain failure reason of operation call or raised error.")
    fallback = ErrorFallbackBodySchema(
        missing=colander.drop,
        description="Additional details to explain failure reason of fallback operation to cleanup call error.")


class InternalServerErrorResponseBodySchema(ErrorResponseBodySchema):
    def __init__(self, **kw):
        kw["code"] = HTTPInternalServerError.code
        super(InternalServerErrorResponseBodySchema, self).__init__(**kw)


class BadRequestResponseSchema(BaseResponseSchemaAPI):
    description = "Required value for request is missing."
    body = ErrorResponseBodySchema(code=HTTPBadRequest.code, description=description)


class UnauthorizedResponseBodySchema(ErrorResponseBodySchema):
    def __init__(self, **kw):
        kw["code"] = HTTPUnauthorized.code
        super(UnauthorizedResponseBodySchema, self).__init__(**kw)

    route_name = colander.SchemaNode(colander.String(), description="Specified API route.")
    request_url = colander.SchemaNode(colander.String(), description="Specified request URL.")


class UnauthorizedResponseSchema(BaseResponseSchemaAPI):
    description = "Unauthorized access to this resource. Missing authentication headers or cookies."
    body = UnauthorizedResponseBodySchema(code=HTTPUnauthorized.code, description=description)


class HTTPForbiddenResponseSchema(BaseResponseSchemaAPI):
    description = "Forbidden operation for this resource or insufficient user privileges."
    body = ErrorResponseBodySchema(code=HTTPForbidden.code, description=description)


class NotFoundResponseSchema(BaseResponseSchemaAPI):
    description = "The route resource could not be found."
    body = ErrorResponseBodySchema(code=HTTPNotFound.code, description=description)


class MethodNotAllowedResponseSchema(BaseResponseSchemaAPI):
    description = "The method is not allowed for this resource."
    body = ErrorResponseBodySchema(code=HTTPMethodNotAllowed.code, description=description)


class NotAcceptableResponseSchema(BaseResponseSchemaAPI):
    description = "Unsupported Content-Type in 'Accept' header was specified."
    body = ErrorResponseBodySchema(code=HTTPNotAcceptable.code, description=description)


class UnprocessableEntityResponseSchema(BaseResponseSchemaAPI):
    description = "Invalid value specified."
    body = ErrorResponseBodySchema(code=HTTPUnprocessableEntity.code, description=description)


class InternalServerErrorResponseSchema(BaseResponseSchemaAPI):
    description = "Internal Server Error. Unhandled exception occurred."
    body = ErrorResponseBodySchema(code=HTTPInternalServerError.code, description=description)


class PermissionSchema(colander.SchemaNode):
    description = "Managed permission under a service."
    schema_type = colander.String
    example = "test-permission"


class PermissionListSchema(colander.SequenceSchema):
    description = "List of managed permissions under a service."
    permission = PermissionSchema()


class ResourceSchema(colander.SchemaNode):
    description = "Managed resource under a service."
    schema_type = colander.String
    example = "test-resource"


class ResourceListSchema(colander.SequenceSchema):
    description = "List of managed resources under a service."
    resource = ResourceSchema()


class ServiceSummarySchema(colander.SchemaNode):
    description = "Managed service."
    schema_type = colander.String
    example = "test-service"


class ServiceListSchema(colander.SequenceSchema):
    description = "List of managed services."
    service = colander.SchemaNode(
        colander.String(),
        description="Name of the service.",
        example="thredds"
    )


class ServiceConfigurationSchema(colander.MappingSchema):
    description = "Custom configuration of the service. Expected format and fields specific to each service type."
    missing = colander.drop
    default = colander.null


class ServiceDetailSchema(colander.MappingSchema):
    name = colander.SchemaNode(
        colander.String(),
        description="Name of the service",
        example="thredds"
    )
    type = colander.SchemaNode(
        colander.String(),
        description="Type of the service",
        example="thredds"
    )
    url = colander.SchemaNode(
        colander.String(),
        missing=colander.drop,  # if listed with corresponding scope (users/groups/admin)
        description="URL of the service (restricted access)",
        example="http://localhost:9999/thredds"
    )
    resources = ResourceListSchema()
    permissions = PermissionListSchema()


class Services_GET_RequestSchema(BaseRequestSchemaAPI):
    pass


class Services_GET_ResponseBodySchema(BaseResponseBodySchema):
    services = ServiceListSchema()


class Services_GET_OkResponseSchema(BaseResponseSchemaAPI):
    description = "Get services successful."
    body = Services_GET_ResponseBodySchema(code=HTTPOk.code, description=description)


class Services_GET_BadRequestResponseSchema(BaseResponseSchemaAPI):
    description = "Invalid service name."
    body = ErrorResponseBodySchema(code=HTTPBadRequest.code, description=description)


class Services_POST_RequestBodySchema(ServiceDetailSchema):
    pass  # FIXME: define fields with derived from MappingSchema if request accepts different fields


class Services_POST_RequestSchema(BaseRequestSchemaAPI):
    body = Services_POST_RequestBodySchema()


class Services_POST_CreatedResponseSchema(BaseResponseSchemaAPI):
    description = "Service creation successful."
    body = BaseResponseBodySchema(code=HTTPOk.code, description=description)


class Services_POST_BadRequestResponseSchema(BaseResponseSchemaAPI):
    description = "Invalid value parameters for service creation."
    body = ErrorResponseBodySchema(code=HTTPBadRequest.code, description=description)


class Service_SummaryBodyResponseSchema(BaseResponseBodySchema):
    service = ServiceSummarySchema()


class Service_GET_RequestSchema(BaseRequestSchemaAPI):
    path = Service_RequestPathSchema()


class Service_GET_ResponseBodySchema(BaseResponseBodySchema):
    service = ServiceDetailSchema()


class Service_GET_OkResponseSchema(BaseResponseSchemaAPI):
    description = "Get service successful."
    body = Service_GET_ResponseBodySchema(code=HTTPOk.code, description=description)


class Service_GET_NotFoundResponseSchema(BaseResponseSchemaAPI):
    description = "Could not find specified service."
    body = ErrorResponseBodySchema(code=HTTPNotFound.code, description=description)


class Services_POST_ForbiddenResponseSchema(BaseResponseSchemaAPI):
    description = "Service registration forbidden."
    body = ErrorResponseBodySchema(code=HTTPForbidden.code, description=description)


class Services_POST_ConflictResponseSchema(BaseResponseSchemaAPI):
    description = "Specified 'service_name' value already exists."
    body = ErrorResponseBodySchema(code=HTTPConflict.code, description=description)


class Services_POST_UnprocessableEntityResponseSchema(BaseResponseSchemaAPI):
    description = "Service creation for registration failed."
    body = ErrorResponseBodySchema(code=HTTPUnprocessableEntity.code, description=description)


class Services_POST_InternalServerErrorResponseSchema(BaseResponseSchemaAPI):
    description = "Service registration status could not be validated."
    body = ErrorResponseBodySchema(code=HTTPInternalServerError.code, description=description)


class Service_PATCH_RequestBodySchema(ServiceDetailSchema):
    pass  # FIXME: define fields with derived from MappingSchema if request accepts different fields


class Service_PATCH_RequestSchema(BaseRequestSchemaAPI):
    path = Service_RequestPathSchema()
    body = Service_PATCH_RequestBodySchema()


class Service_PATCH_ResponseBodySchema(Service_GET_ResponseBodySchema):
    pass  # FIXME: define fields with derived from MappingSchema if request accepts different fields


class Service_PATCH_OkResponseSchema(BaseResponseSchemaAPI):
    description = "Update service successful."
    body = Service_PATCH_ResponseBodySchema(code=HTTPOk.code, description=description)


class Service_PATCH_BadRequestResponseSchema(BaseResponseSchemaAPI):
    description = "Registered service values are already equal to update values."
    body = ErrorResponseBodySchema(code=HTTPBadRequest.code, description=description)


class Service_PATCH_ForbiddenResponseSchema_ReservedKeyword(BaseResponseSchemaAPI):
    description = "Update service name to 'types' not allowed (reserved keyword)."
    body = ErrorResponseBodySchema(code=HTTPForbidden.code, description=description)


class Service_PATCH_ForbiddenResponseSchema(BaseResponseSchemaAPI):
    description = "Update service failed during value assignment."
    body = ErrorResponseBodySchema(code=HTTPForbidden.code, description=description)


class Service_PATCH_UnprocessableEntityResponseSchema(Services_POST_UnprocessableEntityResponseSchema):
    pass


class UserWebhook_POST_RequestBodySchema(colander.MappingSchema):
    event = colander.SchemaNode(
        colander.String(),
        description="User event.",
        validator=colander.OneOf(ValidOperations.values())
    )
    user_name = colander.SchemaNode(
        colander.String(),
        description="User name being created or deleted."
    )
    callback_url = colander.SchemaNode(
        colander.String(),
        description="Callback url to call in case of error while handling user creation.",
        missing=colander.drop
    )


class UserWebhook_POST_RequestSchema(BaseRequestSchemaAPI):
    body = UserWebhook_POST_RequestBodySchema()


class UserWebhook_POST_BadRequestResponseSchema(BaseResponseSchemaAPI):
    description = "Invalid value parameters for user webhook."
    body = ErrorResponseBodySchema(code=HTTPBadRequest.code, description=description)


class UserWebhook_POST_OkResponseSchema(BaseResponseSchemaAPI):
    description = "User event successfully handled."
    body = BaseResponseBodySchema(code=HTTPOk.code, description=description)


class PermissionWebhook_POST_RequestBodySchema(colander.MappingSchema):
    event = colander.SchemaNode(
        colander.String(),
        description="Permission event.",
        validator=colander.OneOf(ValidOperations.values())
    )
    service_name = colander.SchemaNode(
        colander.String(),
        description="Service name of the resource affected by the permission update."
    )
    resource_id = colander.SchemaNode(
        colander.String(),
        description="Id of the resource affected by the permission update."
    )
    resource_full_name = colander.SchemaNode(
        colander.String(),
        description="Full resource name including parents of the resource affected by the permission update.",
        example="thredds/birdhouse/file.nc"
    )
    name = colander.SchemaNode(
        colander.String(),
        description="Permission name applicable to the service/resource.",
        example="read"
    )
    access = colander.SchemaNode(
        colander.String(),
        description="Permission access rule to the service/resource.",
        example="allow"
    )
    scope = colander.SchemaNode(
        colander.String(),
        description="Permission scope over service/resource tree hierarchy.",
        example="recursive"
    )
    user = colander.SchemaNode(
        colander.String(),
        description="User name for which the permission is applied or dropped. (User or group must be provided).",
        missing=colander.drop
    )
    group = colander.SchemaNode(
        colander.String(),
        description="Group name for which the permission is applied or dropped. (User or group must be provided).",
        missing=colander.drop
    )


class PermissionWebhook_POST_RequestSchema(BaseRequestSchemaAPI):
    body = PermissionWebhook_POST_RequestBodySchema()


class PermissionWebhook_POST_BadRequestResponseSchema(BaseResponseSchemaAPI):
    description = "Invalid value parameters for permission webhook."
    body = ErrorResponseBodySchema(code=HTTPBadRequest.code, description=description)


class PermissionWebhook_POST_OkResponseSchema(BaseResponseSchemaAPI):
    description = "Permission event successfully handled."
    body = BaseResponseBodySchema(code=HTTPOk.code, description=description)


class Version_GET_ResponseBodySchema(BaseResponseBodySchema):
    version = colander.SchemaNode(
        colander.String(),
        description="Cowbird API version string",
        example=__meta__.__version__)
    worker_version = colander.SchemaNode(
        colander.String(),
        description="Cowbird worker version string",
        example=__meta__.__version__,
        default=None)
    db_version = colander.SchemaNode(
        colander.String(),
        description="Database version string",
        exemple="a395ef9d3fe6")
    version_detail = colander.SchemaNode(
        colander.String(),
        description="Version detail string")


class Version_GET_OkResponseSchema(BaseResponseSchemaAPI):
    description = "Get version successful."
    body = Version_GET_ResponseBodySchema(code=HTTPOk.code, description=description)


class Homepage_GET_OkResponseSchema(BaseResponseSchemaAPI):
    description = "Get homepage successful."
    body = BaseResponseBodySchema(code=HTTPOk.code, description=description)


class SwaggerAPI_GET_OkResponseSchema(colander.MappingSchema):
    description = TitleAPI
    header = RequestHeaderSchemaUI()
    body = colander.SchemaNode(colander.String(), example="This page!")


# Responses for specific views
Services_GET_responses = {
    "200": Services_GET_OkResponseSchema(),
    "400": Services_GET_BadRequestResponseSchema(),
    "401": UnauthorizedResponseSchema(),
    "406": NotAcceptableResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
Services_POST_responses = {
    "201": Services_POST_CreatedResponseSchema(),
    "400": Services_POST_BadRequestResponseSchema(),
    "401": UnauthorizedResponseSchema(),
    "403": Services_POST_ForbiddenResponseSchema(),
    "406": NotAcceptableResponseSchema(),
    "409": Services_POST_ConflictResponseSchema(),
    "422": Services_POST_UnprocessableEntityResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
Service_GET_responses = {
    "200": Service_GET_OkResponseSchema(),
    "401": UnauthorizedResponseSchema(),
    "404": Service_GET_NotFoundResponseSchema(),
    "406": NotAcceptableResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
Service_PATCH_responses = {
    "200": Service_PATCH_OkResponseSchema(),
    "400": Service_PATCH_BadRequestResponseSchema(),
    "401": UnauthorizedResponseSchema(),
    "403": Service_PATCH_ForbiddenResponseSchema(),
    "406": NotAcceptableResponseSchema(),
    "422": Service_PATCH_UnprocessableEntityResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
UserWebhook_POST_responses = {
    "200": UserWebhook_POST_OkResponseSchema(),
    "400": UserWebhook_POST_BadRequestResponseSchema(),
    "406": NotAcceptableResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
PermissionWebhook_POST_responses = {
    "200": PermissionWebhook_POST_OkResponseSchema(),
    "400": PermissionWebhook_POST_BadRequestResponseSchema(),
    "406": NotAcceptableResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
Version_GET_responses = {
    "200": Version_GET_OkResponseSchema(),
    "406": NotAcceptableResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
Homepage_GET_responses = {
    "200": Homepage_GET_OkResponseSchema(),
    "406": NotAcceptableResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
SwaggerAPI_GET_responses = {
    "200": SwaggerAPI_GET_OkResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
