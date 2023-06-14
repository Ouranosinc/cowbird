from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPError, HTTPInternalServerError, HTTPUnprocessableEntity

from cowbird.api import exception as ax
from cowbird.api import schemas as s
from cowbird.utils import CONTENT_TYPE_JSON, get_logger

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from typing import Any, Iterable, Optional, Type, Union

    from pyramid.request import Request

LOGGER = get_logger(__name__)


def check_value(value, param_name, check_type=str, pattern=ax.PARAM_REGEX, http_error=None, msg_on_fail=None):
    # type: (Any, str, Any, Optional[Union[str, bool]], Optional[Type[HTTPError]], Optional[str]) -> None
    """
    Validates the value against specified type and pattern.

    :param value: value to validate.
    :param check_type: verify that parameter value is of specified type. Set to ``None`` to disable check.
    :param pattern: regex pattern to validate the input with.
        If value evaluates to ``False``, skip this kind of validation (default: :py:data:`ax.PARAM_REGEX`).
    :param param_name: path variable key.
    :param http_error: derived exception to raise on check failure (default: :class:`HTTPUnprocessableEntity`)
    :param msg_on_fail: message details to return in HTTP exception if check failed
        (default: description message of :class:`UnprocessableEntityResponseSchema`).
    :returns: None.
    :raises HTTPError: if the key is not an applicable path variable for this request.
    """
    if not http_error:
        http_error = HTTPUnprocessableEntity
    if not msg_on_fail:
        msg_on_fail = s.UnprocessableEntityResponseSchema.description
    not_none = (type(None) not in check_type if isinstance(check_type, tuple)
                else not isinstance(check_type, type(None)))
    ax.verify_param(value, not_none=not_none, is_type=bool(check_type), param_compare=check_type, param_name=param_name,
                    http_error=http_error, msg_on_fail=msg_on_fail)
    if bool(pattern) and check_type == str:
        ax.verify_param(value, not_empty=True, matches=True, param_name=param_name, param_compare=pattern,
                        http_error=http_error, msg_on_fail=msg_on_fail)


def get_request_method_content(request):
    # 'request' object stores GET content into 'GET' property, while other methods are in 'POST' property
    method_property = "GET" if request.method == "GET" else "POST"
    return getattr(request, method_property)


def get_multiformat_body_raw(request, key, default=None):
    # type: (Request, str, Optional[Any]) -> Any
    """
    Obtains the value of :paramref:`key` element from the request body according to specified `Content-Type` header.

    .. seealso::
        - :func:`get_multiformat_body`
    """
    msg = f"Key '{repr(key)}' could not be extracted from '{request.method}' of type '{request.content_type}'"
    if request.content_type == CONTENT_TYPE_JSON:
        # avoid json parse error if body is empty
        if not len(request.body):
            return default
        return ax.evaluate_call(lambda: request.json.get(key, default),
                                http_error=HTTPInternalServerError, msg_on_fail=msg)
    return ax.evaluate_call(lambda: get_request_method_content(request).get(key, default),
                            http_error=HTTPInternalServerError, msg_on_fail=msg)


def get_multiformat_body(request, key, default=None, check_type=str, pattern=ax.PARAM_REGEX,
                         http_error=None, msg_on_fail=None):
    # type: (Request, str, Any, Any, Optional[Union[str, bool]], Optional[Type[HTTPError]], Optional[str]) -> Any
    """
    Obtains and validates the matched value under :paramref:`key` element from the request body.

    Parsing of the body is accomplished according to ``Content-Type`` header.

    :param request: request from which to retrieve the key.
    :param key: body key variable.
    :param default: value to return instead if not found. If this default is ``None``, it will raise.
    :param check_type: verify that parameter value is of specified type. Set to ``None`` to disable check.
    :param pattern: regex pattern to validate the input with.
        If value evaluates to ``False``, skip this kind of validation
        (default: :py:data:`cowbird.api.exception.PARAM_REGEX`).
    :param http_error: derived exception to raise on check failure (default: :class:`HTTPUnprocessableEntity`)
    :param msg_on_fail: message details to return in HTTP exception if check failed
        (default: description message of :class:`UnprocessableEntityResponseSchema`).
    :returns: matched path variable value.
    :raises HTTPBadRequest: if the key could not be retrieved from the request body and has no provided default value.
    :raises HTTPUnprocessableEntity: if the retrieved value from the key is invalid for this request.

    .. seealso::
        - :func:`get_multiformat_body_raw`
    """
    val = get_multiformat_body_raw(request, key, default=default)
    check_value(val, key, check_type, pattern, http_error=http_error, msg_on_fail=msg_on_fail)
    return val


def get_path_param(request, key, check_type=str, pattern=ax.PARAM_REGEX, http_error=None, msg_on_fail=None):
    # type: (Request, str, Any, Optional[Union[str, bool]], Optional[Type[HTTPError]], Optional[str]) -> str
    """
    Obtains the matched value located at the expected position of the specified path variable.

    :param request: request from which to retrieve the key.
    :param key: path variable key.
    :param check_type: verify that parameter value is of specified type. Set to ``None`` to disable check.
    :param pattern: regex pattern to validate the input with.
        If value evaluates to ``False``, skip this kind of validation (default: :py:data:`ax.PARAM_REGEX`).
    :param http_error: derived exception to raise on check failure (default: :class:`HTTPUnprocessableEntity`)
    :param msg_on_fail: message details to return in HTTP exception if check failed
        (default: description message of :class:`UnprocessableEntityResponseSchema`).
    :returns: matched path variable value.
    :raises HTTPError: if the key is not an applicable path variable for this request.
    """
    val = request.matchdict.get(key)
    check_value(val, key, check_type, pattern, http_error=http_error, msg_on_fail=msg_on_fail)
    return val


def get_query_param(request, case_insensitive_key, default=None):
    # type: (Request, Union[str, Iterable[str]], Optional[Any]) -> Any
    """
    Retrieves a query string value by name (case insensitive), or returns the default if not present.
    """
    if not isinstance(case_insensitive_key, (list, set, tuple)):
        case_insensitive_key = [case_insensitive_key]
    for param in request.params:
        for key in case_insensitive_key:
            if param.lower() == key.lower():
                return request.params.get(param)
    return default
