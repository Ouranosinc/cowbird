import requests
from pyramid.httpexceptions import HTTPBadRequest, HTTPOk
from pyramid.view import view_config

from cowbird.api import exception as ax
from cowbird.api import requests as ar
from cowbird.api import schemas as s
from cowbird.api.schemas import ValidOperations
from cowbird.permissions_synchronizer import Permission
from cowbird.services.service_factory import ServiceFactory
from cowbird.utils import get_logger

LOGGER = get_logger(__name__)


def dispatch(svc_fct, fct_name):
    exceptions = []
    for svc in ServiceFactory().get_active_services():
        # Allow every service to be notified even if one of them throw an error
        try:
            LOGGER.info("Dispatching event [%s] for service [%s]", fct_name, svc.name)
            svc_fct(svc)
        except Exception as exception:  # noqa
            exceptions.append(exception)
            LOGGER.error("Exception raised while handling event [%s] for service [%s] : [%r]",
                         fct_name, svc.name, exception)
    if exceptions:
        raise Exception(exceptions)


@s.UserWebhookAPI.post(schema=s.UserWebhook_POST_RequestSchema, tags=[s.WebhooksTag],
                       response_schemas=s.UserWebhook_POST_responses)
@view_config(route_name=s.UserWebhookAPI.name, request_method="POST")
def post_user_webhook_view(request):
    """
    User webhook used for created or removed user events.
    """
    event = ar.get_multiformat_body(request, "event")
    ax.verify_param(event, param_name="event",
                    param_compare=ValidOperations.values(),
                    is_in=True,
                    http_error=HTTPBadRequest,
                    msg_on_fail=s.UserWebhook_POST_BadRequestResponseSchema.description)
    user_name = ar.get_multiformat_body(request, "user_name")
    if event == ValidOperations.CreateOperation.value:
        # FIXME: Tried with ax.URL_REGEX, but cannot match what seems valid urls...
        callback_url = ar.get_multiformat_body(request, "callback_url", pattern=None)
        try:
            dispatch(lambda svc: svc.user_created(user_name=user_name), "user_created")
        except Exception:  # noqa
            # If something bad happens, set the status as erroneous in Magpie
            LOGGER.warning("Exception occurs while dispatching event, calling Magpie callback url : [%s]", callback_url)
            requests.get(callback_url)
            # TODO: return something else than 200
    else:
        dispatch(lambda svc: svc.user_deleted(user_name=user_name), "user_deleted")
    return ax.valid_http(HTTPOk, detail=s.UserWebhook_POST_OkResponseSchema.description)


@s.PermissionWebhookAPI.post(schema=s.PermissionWebhook_POST_RequestSchema, tags=[s.WebhooksTag],
                             response_schemas=s.PermissionWebhook_POST_responses)
@view_config(route_name=s.PermissionWebhookAPI.name, request_method="POST")
def post_permission_webhook_view(request):
    """
    Permission webhook used for created or removed permission events.
    """
    event = ar.get_multiformat_body(request, "event")
    ax.verify_param(event, param_name="event",
                    param_compare=ValidOperations.values(),
                    is_in=True,
                    http_error=HTTPBadRequest,
                    msg_on_fail=s.PermissionWebhook_POST_BadRequestResponseSchema.description)
    service_name = ar.get_multiformat_body(request, "service_name")
    resource_id = ar.get_multiformat_body(request, "resource_id")
    param_regex_with_slashes = r"^/?[A-Za-z0-9]+(?:[\s_\-\./][A-Za-z0-9]+)*$"
    resource_full_name = ar.get_multiformat_body(request, "resource_full_name",
                                                 pattern=param_regex_with_slashes)
    name = ar.get_multiformat_body(request, "name")
    access = ar.get_multiformat_body(request, "access")
    scope = ar.get_multiformat_body(request, "scope")
    user = ar.get_multiformat_body(request, "user")
    group = None
    if user:
        ar.check_value(user, "user")
    else:
        group = ar.get_multiformat_body(request, "group")

    permission = Permission(
        service_name=service_name,
        resource_id=resource_id,
        resource_full_name=resource_full_name,
        name=name,
        access=access,
        scope=scope,
        user=user,
        group=group
    )
    if event == ValidOperations.CreateOperation.value:
        dispatch(lambda svc: svc.permission_created(permission=permission), "permission_created")
    else:
        dispatch(lambda svc: svc.permission_deleted(permission=permission), "permission_deleted")
    return ax.valid_http(HTTPOk, detail=s.PermissionWebhook_POST_OkResponseSchema.description)
