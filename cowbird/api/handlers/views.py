from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPOk
from pyramid.request import Request
from pyramid.view import view_config

from cowbird.api import exception as ax
from cowbird.api import requests as ar
from cowbird.api import schemas as s
from cowbird.handlers import get_handlers
from cowbird.handlers.handler import Handler
from cowbird.typedefs import JSON, AnyResponseType


@s.HandlersAPI.get(schema=s.Handlers_GET_RequestSchema, tags=[s.HandlersTag],
                   response_schemas=s.Handlers_GET_responses)
@view_config(route_name=s.HandlersAPI.name, request_method="GET")
def get_handlers_view(request: Request) -> AnyResponseType:
    """
    List all registered handlers.
    """
    data: JSON = {"handlers": [handler.name for handler in get_handlers(request)]}
    return ax.valid_http(HTTPOk, content=data, detail=s.Handlers_GET_OkResponseSchema.description)


def get_handler(request: Request) -> Handler:
    """
    Get a handler object from the parameters of a request.
    """
    handler_name = ar.get_path_param(request, "handler_name", http_error=HTTPBadRequest,
                                     msg_on_fail=s.Handlers_GET_BadRequestResponseSchema.description)
    handlers = list(filter(lambda handler: handler.name == handler_name, get_handlers(request)))
    ax.verify_param(len(handlers), is_equal=True, param_compare=1, param_name="handler_name",
                    http_error=HTTPNotFound, msg_on_fail=s.Handler_Check_NotFoundResponseSchema.description)
    return handlers[0]


@s.HandlerAPI.get(schema=s.Handler_GET_RequestSchema, tags=[s.HandlersTag],
                  response_schemas=s.Handler_GET_responses)
@view_config(route_name=s.HandlerAPI.name, request_method="GET")
def get_handler_view(request: Request) -> AnyResponseType:
    """
    Get handler details.
    """
    data: JSON = {"handler": get_handler(request).json()}
    return ax.valid_http(HTTPOk, content=data, detail=s.Handlers_GET_OkResponseSchema.description)


@s.HandlerResyncAPI.put(schema=s.HandlerResync_PUT_RequestSchema, tags=[s.HandlersTag],
                        response_schemas=s.HandlerResync_PUT_responses)
@view_config(route_name=s.HandlerResyncAPI.name, request_method="PUT")
def resync_handler_view(request: Request) -> AnyResponseType:
    """
    Resync handler operation.
    """
    get_handler(request).resync()
    return ax.valid_http(HTTPOk, detail=s.HandlerResync_PUT_OkResponseSchema.description)
