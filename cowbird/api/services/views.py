from pyramid.httpexceptions import HTTPOk, HTTPBadRequest, HTTPNotFound
from pyramid.view import view_config

from cowbird.api import exception as ax, requests as ar, schemas as s
from cowbird.api.services.utils import get_services


@s.ServicesAPI.get(schema=s.Services_GET_RequestSchema, tags=[s.ServicesTag],
                   response_schemas=s.Services_GET_responses)
@view_config(route_name=s.ServicesAPI.name, request_method="GET")
def get_services_view(request):
    """
    List all registered services.
    """
    data = {"services": [svc.name for svc in get_services(request)]}
    return ax.valid_http(HTTPOk, content=data, detail=s.Services_GET_OkResponseSchema.description)


@s.ServiceAPI.get(schema=s.Service_GET_RequestSchema, tags=[s.ServicesTag],
                  response_schemas=s.Service_GET_responses)
@view_config(route_name=s.ServiceAPI.name, request_method="GET")
def get_service_view(request):
    """
    Get service details.
    """
    svc_name = ar.get_path_param(request, "service_name", http_error=HTTPBadRequest,
                                 msg_on_fail=s.Services_GET_BadRequestResponseSchema.description)
    services = list(filter(lambda svc: svc.name == svc_name, get_services(request)))
    ax.verify_param(len(services), is_equal=True, param_compare=1, param_name="service_name",
                    http_error=HTTPNotFound, msg_on_fail=s.Service_GET_NotFoundResponseSchema.description)
    data = {"service": services[0].json()}
    return ax.valid_http(HTTPOk, content=data, detail=s.Services_GET_OkResponseSchema.description)
