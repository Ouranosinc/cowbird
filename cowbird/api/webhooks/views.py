import requests
from pyramid.httpexceptions import HTTPBadRequest, HTTPOk
from pyramid.view import view_config

from cowbird.api import exception as ax
from cowbird.api import requests as ar
from cowbird.api import schemas as s
from cowbird.api.schemas import ValidOperations
from cowbird.permissions_synchronizer import Permission
from cowbird.services.service_factory import ServiceFactory


def dispatch(fct_name, kwargs):
    for svc in ServiceFactory().get_active_services():
        fct = getattr(svc, fct_name)
        fct(**kwargs)


@s.UserWebhookAPI.post(schema=s.UserWebhook_POST_RequestSchema, tags=[s.WebhooksTag],
                       response_schemas=s.UserWebhook_POST_responses)
@view_config(route_name=s.UserWebhookAPI.name, request_method="POST")
def post_user_webhook_view(request):
    """
    User webhook used for created or removed user events.
    """
    operation = ar.get_multiformat_body(request, "operation")
    ax.verify_param(operation, param_name="operation",
                    param_compare=ValidOperations.values(),
                    is_in=True,
                    http_error=HTTPBadRequest,
                    msg_on_fail=s.UserWebhook_POST_BadRequestResponseSchema.description)
    user_name = ar.get_multiformat_body(request, "user_name")
    if operation == ValidOperations.CreateOperation.value:
        callback_url = ar.get_multiformat_body(request, "callback_url")
        try:
            dispatch("create_user", dict(user_name=user_name))
        except Exception:  # noqa
            # If something bad happens, set the status as erroneous in Magpie
            requests.get(callback_url)
    else:
        dispatch("delete_user", dict(user_name=user_name))
    return ax.valid_http(HTTPOk, detail=s.UserWebhook_POST_OkResponseSchema.description)


@s.PermissionWebhookAPI.post(schema=s.PermissionWebhook_POST_RequestSchema, tags=[s.WebhooksTag],
                             response_schemas=s.PermissionWebhook_POST_responses)
@view_config(route_name=s.PermissionWebhookAPI.name, request_method="POST")
def post_permission_webhook_view(request):
    """
    Permission webhook used for created or removed permission events.
    """
    operation = ar.get_multiformat_body(request, "operation")
    ax.verify_param(operation, param_name="operation",
                    param_compare=ValidOperations.values(),
                    is_in=True,
                    http_error=HTTPBadRequest,
                    msg_on_fail=s.PermissionWebhook_POST_BadRequestResponseSchema.description)
    service_name = ar.get_multiformat_body(request, "service_name")
    resource_id = ar.get_multiformat_body(request, "resource_id")
    PARAM_REGEX_WITH_SLASHES = r"^/?[A-Za-z0-9]+(?:[\s_\-\./][A-Za-z0-9]+)*$"
    resource_full_name = ar.get_multiformat_body(request, "resource_full_name",
                                                 pattern=PARAM_REGEX_WITH_SLASHES)
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
    if operation == ValidOperations.CreateOperation.value:
        dispatch("create_permission", dict(permission=permission))
    else:
        dispatch("delete_permission", dict(permission=permission))
    return ax.valid_http(HTTPOk, detail=s.PermissionWebhook_POST_OkResponseSchema.description)
