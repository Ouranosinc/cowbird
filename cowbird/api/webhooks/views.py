import inspect
import traceback

import requests
from pyramid.httpexceptions import HTTPBadRequest, HTTPInternalServerError, HTTPOk
from pyramid.view import view_config

from cowbird.api import exception as ax
from cowbird.api import requests as ar
from cowbird.api import schemas as s
from cowbird.api.schemas import ValidOperations
from cowbird.handlers import get_handlers, HandlerFactory
from cowbird.permissions_synchronizer import Permission
from cowbird.utils import CONTENT_TYPE_JSON, get_logger, get_ssl_verify, get_timeout

LOGGER = get_logger(__name__)


class WebhookDispatchException(Exception):
    """
    Error indicating that an exception occurred during a webhook dispatch.
    """


def dispatch(handler_fct):
    exceptions = []
    event_name = inspect.getsource(handler_fct).split(":")[1].strip()
    handlers = get_handlers()
    for handler in handlers:
        # Allow every handler to be notified even if one of them throw an error
        try:
            LOGGER.info("Dispatching event [%s] for handler [%s].", event_name, handler.name)
            handler_fct(handler)
        except Exception as exception:  # noqa
            exceptions.append(exception)
            LOGGER.error("Exception raised while handling event [%s] for handler [%s] : [%r].",
                         event_name, handler.name, exception)
            traceback.print_exc()
    if not handlers:
        LOGGER.warning("No handlers matched for dispatch of event [%s].", event_name)
    if exceptions:
        raise WebhookDispatchException(exceptions)


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
    LOGGER.debug("Received user webhook event [%s] for user [%s].", event, user_name)
    if event == ValidOperations.CreateOperation.value:
        # FIXME: Tried with ax.URL_REGEX, but cannot match what seems valid urls...
        callback_url = ar.get_multiformat_body(request, "callback_url", pattern=None)

        def handler_fct(handler):
            handler.user_created(user_name=user_name)
    else:
        callback_url = None

        def handler_fct(handler):
            handler.user_deleted(user_name=user_name)
    try:
        dispatch(handler_fct)
    except Exception as dispatch_exc:  # noqa
        if callback_url:
            # If something bad happens, set the status as erroneous in Magpie
            LOGGER.warning("Exception occurred while dispatching event [%s], "
                           "calling Magpie callback url : [%s]", event, callback_url, exc_info=dispatch_exc)
            try:
                requests.head(callback_url, verify=get_ssl_verify(request), timeout=get_timeout(request))
            except requests.exceptions.RequestException as exc:
                LOGGER.warning("Cannot complete the Magpie callback url request to [%s] : [%s]", callback_url, exc)
        else:
            LOGGER.warning("Exception occurred while dispatching event [%s].", event, exc_info=dispatch_exc)
        ax.raise_http(HTTPInternalServerError,
                      detail=s.UserWebhook_POST_InternalServerErrorResponseSchema.description,
                      content_type=CONTENT_TYPE_JSON,
                      content={
                          "webhook": request.json_body,
                          "exception": repr(dispatch_exc)
                      })
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
    # Use raw value for service name, to avoid errors with `None` values
    # when the permission is not applied to a `service` type resource.
    service_name = ar.get_multiformat_body_raw(request, "service_name")
    resource_id = ar.get_multiformat_body(request, "resource_id", check_type=int)

    # TODO: The service_type should probably be sent directly in the webhook from Magpie.
    magpie = HandlerFactory().get_handler("Magpie")
    res_tree = magpie.get_parents_resource_tree(resource_id)
    service_type = magpie.get_service_info(res_tree[0]["resource_name"])["service_type"]

    param_regex_with_slashes = r"^/?[A-Za-z0-9]+(?:[\s_\-\./:][A-Za-z0-9]+)*$"
    resource_full_name = ar.get_multiformat_body(request, "resource_full_name",
                                                 pattern=param_regex_with_slashes)
    name = ar.get_multiformat_body(request, "name")
    access = ar.get_multiformat_body(request, "access")
    scope = ar.get_multiformat_body(request, "scope")
    user = ar.get_multiformat_body_raw(request, "user")
    group = ar.get_multiformat_body_raw(request, "group")
    ax.verify_param(bool(user or group), is_true=True, http_error=HTTPBadRequest,
                    msg_on_fail=s.PermissionWebhook_POST_BadRequestResponseSchema.description)

    permission = Permission(
        service_name=service_name,
        service_type=service_type,
        resource_id=resource_id,
        resource_full_name=resource_full_name,
        name=name,
        access=access,
        scope=scope,
        user=user,
        group=group
    )
    LOGGER.debug("Received permission webhook event [%s] for [%s].", event, permission)
    if event == ValidOperations.CreateOperation.value:
        dispatch(lambda handler: handler.permission_created(permission=permission))
    else:
        dispatch(lambda handler: handler.permission_deleted(permission=permission))
    return ax.valid_http(HTTPOk, detail=s.PermissionWebhook_POST_OkResponseSchema.description)
