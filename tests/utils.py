import functools
import json as json_pkg  # avoid conflict name with json argument employed for some function
import os
from stat import ST_MODE
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import mock
import requests
import requests.exceptions
from packaging.version import Version as LooseVersion
from pyramid.httpexceptions import HTTPException
from pyramid.testing import DummyRequest
from pyramid.testing import setUp as PyramidSetUp
from webtest.app import AppError, TestApp  # noqa
from webtest.response import TestResponse

from cowbird.app import get_app
from cowbird.constants import COWBIRD_ROOT, get_constant
from cowbird.handlers.handler import Handler
from cowbird.utils import (
    CONTENT_TYPE_JSON,
    USE_TEST_CELERY_APP_CFG,
    SingletonMeta,
    get_header,
    get_settings_from_config_ini,
    is_null,
    null
)

# employ example INI config for tests where needed to ensure that configurations are valid
TEST_INI_FILE = os.path.join(COWBIRD_ROOT, "config/cowbird.example.ini")
TEST_CFG_FILE = os.path.join(COWBIRD_ROOT, "config/config.example.yml")


class TestAppContainer(object):
    test_app = None  # type: Optional[TestApp]
    app = None       # type: Optional[TestApp]
    url = None       # type: Optional[str]


if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from typing import Any, Callable, Collection, Dict, Iterable, List, Literal, Optional, Tuple, Type, TypeAlias, Union

    from packaging.version import _Version as TupleVersion
    from pyramid.request import Request

    from cowbird.typedefs import JSON, AnyCookiesType, AnyHeadersType, AnyResponseType, HeadersType, SettingsType
    from cowbird.utils import NullType

    # pylint: disable=C0103,invalid-name
    TestAppOrUrlType = Union[str, TestApp]
    AnyTestItemType = Union[TestAppOrUrlType, TestAppContainer]

    _TestVersion = "TestVersion"  # type: TypeAlias   # pylint: disable=C0103
    LatestVersion = Literal["latest"]
    AnyTestVersion = Union[str, Iterable[str], LooseVersion, _TestVersion, LatestVersion]


class TestVersion(LooseVersion):
    """
    Special version supporting ``latest`` keyword to ignore safeguard check of :func:`warn_version` during development.

    .. seealso::
        Environment variable ``COWBIRD_TEST_VERSION`` should be set with the desired version or ``latest`` to evaluate
        even new features above the last tagged version.
    """
    __test__ = False  # avoid invalid collect depending on specified input path/items to pytest

    def __init__(self, vstring):
        # type: (AnyTestVersion) -> None
        if hasattr(vstring, "__iter__") and not isinstance(vstring, str):
            vstring = ".".join(str(part) for part in vstring)
        if isinstance(vstring, (TestVersion, LooseVersion)):
            self.version = vstring.version
            return
        if vstring == "latest":
            self.version = vstring  # noqa
            return
        super(TestVersion, self).__init__(vstring)

    def _cmp(self, other):
        # type: (Any) -> int
        if not isinstance(other, TestVersion):
            other = TestVersion(other)
        if self.version == "latest" and other.version == "latest":
            return 0
        if self.version == "latest":
            return 1
        if other.version == "latest":
            return -1
        if super(TestVersion, self).__lt__(other):
            return -1
        if super(TestVersion, self).__gt__(other):
            return 1
        return 0

    def __lt__(self, other):
        # type: (Any) -> bool
        return self._cmp(other) < 0

    def __le__(self, other):
        # type: (Any) -> bool
        return self._cmp(other) <= 0

    def __gt__(self, other):
        # type: (Any) -> bool
        return self._cmp(other) > 0

    def __ge__(self, other):
        # type: (Any) -> bool
        return self._cmp(other) >= 0

    def __eq__(self, other):
        # type: (Any) -> bool
        return self._cmp(other) == 0

    def __ne__(self, other):
        # type: (Any) -> bool
        return self._cmp(other) != 0

    @property
    def version(self):
        # type: () -> Union[Tuple[Union[int, str], ...], str]
        if self._version == "latest":
            return "latest"
        return self._version

    @version.setter
    def version(self, version):
        # type: (Union[Tuple[Union[int, str], ...], str, TupleVersion]) -> None
        if version == "latest":
            self._version = "latest"
        else:
            self.__init__(version)  # pylint: disable=C2801


class MockMagpieHandler(Handler):
    required_params = []

    def __init__(self, settings, name, **kwargs):
        super(MockMagpieHandler, self).__init__(settings, name, **kwargs)
        self.event_users = []
        self.event_perms = []
        self.outbound_perms = []

    def json(self):
        return {"name": self.name,
                "event_users": self.event_users,
                "event_perms": self.event_perms,
                "outbound_perms": self.outbound_perms}

    def get_resource_id(self, resource_full_name):
        pass

    def get_geoserver_workspace_res_id(self, user_name):
        pass

    def user_created(self, user_name):
        self.event_users.append(user_name)

    def user_deleted(self, user_name):
        self.event_users.remove(user_name)

    def permission_created(self, permission):
        self.event_perms.append(permission.resource_full_name)

    def permission_deleted(self, permission):
        self.event_perms.remove(permission.resource_full_name)

    def create_permission(self, permission):
        self.outbound_perms.append(permission)

    def delete_permission(self, permission):
        for perm in self.outbound_perms:
            if perm == permission:
                self.outbound_perms.remove(perm)
                return

    def delete_resource(self, res_id):
        pass

    def get_service_types(self):
        # type: () -> List
        """
        Returns the list of service types available on Magpie.
        """
        # Hardcoded listed of currently available services on Magpie.
        return ["access", "api", "geoserver", "geoserverwfs", "geoserverwms", "geoserverwps", "ncwms", "thredds",
                "wfs", "wps"]


class MockAnyHandlerBase(Handler):  # noqa  # missing abstract method 'required_params'
    ResourceId = 1000

    def get_resource_id(self, resource_full_name):
        return MockAnyHandler.ResourceId

    def user_created(self, user_name):
        pass

    def user_deleted(self, user_name):
        pass

    def permission_created(self, permission):
        pass

    def permission_deleted(self, permission):
        pass


class MockAnyHandler(MockAnyHandlerBase):
    required_params = []


def clear_handlers_instances():
    # Remove the handler instances initialized with test specific config
    SingletonMeta._instances.clear()  # pylint: disable=W0212


def config_setup_from_ini(config_ini_file_path):
    settings = get_settings_from_config_ini(config_ini_file_path)
    config = PyramidSetUp(settings=settings)
    return config


def get_test_app(settings=None):
    # type: (Optional[SettingsType]) -> TestApp
    """
    Instantiate a local test application.
    """
    config = config_setup_from_ini(TEST_INI_FILE)
    config.registry.settings["cowbird.url"] = "http://localhost:80"
    config.registry.settings["cowbird.ini_file_path"] = TEST_INI_FILE
    config.registry.settings["cowbird.config_path"] = TEST_CFG_FILE
    config.registry.settings["mongo_uri"] = "mongodb://{host}:{port}/{db_name}".format(  # pylint: disable=C0209
        host=os.getenv("COWBIRD_TEST_DB_HOST", "127.0.0.1"),
        port=os.getenv("COWBIRD_TEST_DB_PORT", "27017"),
        db_name=os.getenv("COWBIRD_TEST_DB_NAME", "cowbird-test")
    )
    # For test, we want to use the real Celery app which is properly mocked
    # By setting the internal setting USE_TEST_CELERY_APP_CFG to true, the pyramid celery app will not be used
    config.registry.settings[USE_TEST_CELERY_APP_CFG] = True
    if settings:
        config.registry.settings.update(settings)

    test_app = TestApp(get_app({}, **config.registry.settings))
    return test_app


def get_app_or_url(test_item):
    # type: (AnyTestItemType) -> TestAppOrUrlType
    """
    Obtains the referenced test application, local application or remote URL from `Test Case` implementation.
    """
    if isinstance(test_item, (TestApp, str)):
        return test_item
    test_app = getattr(test_item, "test_app", None)
    if test_app and isinstance(test_app, TestApp):
        return test_app
    app_or_url = getattr(test_item, "app", None) or getattr(test_item, "url", None)
    if not app_or_url:
        raise ValueError("Invalid test class, application or URL could not be found.")
    return app_or_url


def get_hostname(test_item):
    # type: (AnyTestItemType) -> str
    """
    Obtains stored hostname in the class implementation.
    """
    app_or_url = get_app_or_url(test_item)
    if isinstance(app_or_url, TestApp):
        app_or_url = get_constant("COWBIRD_URL", app_or_url.app.registry)
    return str(urlparse(app_or_url).hostname)


def get_headers(app_or_url, header_dict):
    # type: (TestAppOrUrlType, AnyHeadersType) -> HeadersType
    """
    Obtains stored headers in the class implementation.
    """
    if isinstance(app_or_url, TestApp):
        return dict(header_dict.items())  # noqa
    return header_dict


def get_response_content_types_list(response):
    # type: (AnyResponseType) -> List[str]
    """
    Obtains the specified response Content-Type header(s) without additional formatting parameters.
    """
    content_types = []
    known_types = ["application", "audio", "font", "example", "image", "message", "model", "multipart", "text", "video"]
    for part in response.headers["Content-Type"].split(";"):
        for sub_type in part.strip().split(","):
            if "=" not in sub_type and sub_type.split("/")[0] in known_types:
                content_types.append(sub_type)
    return content_types


def get_json_body(response):
    # type: (AnyResponseType) -> JSON
    """
    Obtains the JSON payload of the response regardless of its class implementation.
    """
    if isinstance(response, TestResponse):
        return response.json
    return response.json()


def json_msg(json_body, msg=null):
    # type: (JSON, Optional[str]) -> str
    """
    Generates a message string with formatted JSON body for display with easier readability.
    """
    json_str = json_pkg.dumps(json_body, indent=4, ensure_ascii=False)
    if msg is not null:
        return f"{msg}\n{json_str}"
    return json_str


def mock_get_settings(test):
    """
    Decorator to mock :func:`cowbird.utils.get_settings` to allow retrieval of settings from :class:`DummyRequest`.

    .. warning::
        Only apply on test methods (not on class TestCase) to ensure that :mod:`pytest` can collect them correctly.
    """
    from cowbird.utils import get_settings as real_get_settings

    def mocked(container):
        if isinstance(container, DummyRequest):
            return container.registry.settings
        return real_get_settings(container)

    @functools.wraps(test)
    def wrapped(*_, **__):
        # mock.patch("cowbird.handlers.get_settings", side_effect=mocked)
        with mock.patch("cowbird.utils.get_settings", side_effect=mocked):
            return test(*_, **__)
    return wrapped


def mock_request(request_path_query="",     # type: str
                 method="GET",              # type: str
                 params=None,               # type: Optional[Dict[str, str]]
                 body="",                   # type: Union[str, JSON]
                 content_type=None,         # type: Optional[str]
                 headers=None,              # type: Optional[AnyHeadersType]
                 cookies=None,              # type: Optional[AnyCookiesType]
                 settings=None,             # type: SettingsType
                 ):                         # type: (...) -> Request
    """
    Generates a fake request with provided arguments.

    Can be employed by functions that expect a request object as input to retrieve details such as body content, the
    request path, or internal settings, but that no actual request needs to be accomplished.
    """
    parts = request_path_query.split("?")
    path = parts[0]
    query = {}
    if len(parts) > 1 and parts[1]:
        for part in parts[1].split("&"):
            kv = part.split("=")  # handle trailing keyword query arguments without values
            if kv[0]:  # handle invalid keyword missing
                query[kv[0]] = kv[1] if len(kv) > 1 else None
    elif params:
        query = params
    request = DummyRequest(path=path, params=query)
    request.path_qs = request_path_query
    request.method = method
    request.content_type = content_type
    request.headers = headers or {}
    request.cookies = cookies or {}
    request.matched_route = None  # cornice method
    if content_type:
        request.headers["Content-Type"] = content_type
    request.body = body
    try:
        if body:
            # set missing DummyRequest.json attribute
            request.json = json_pkg.loads(body)  # type: ignore
    except (TypeError, ValueError):
        pass
    request.registry.settings = settings or {}
    return request  # noqa  # fake type of what is normally expected just to avoid many 'noqa'


def test_request(test_item,             # type: AnyTestItemType
                 method,                # type: str
                 path,                  # type: str
                 data=None,             # type: Optional[Union[JSON, str]]
                 json=None,             # type: Optional[Union[JSON, str]]
                 body=None,             # type: Optional[Union[JSON, str]]
                 params=None,           # type: Optional[Dict[str, str]]
                 timeout=10,            # type: int
                 retries=3,             # type: int
                 allow_redirects=True,  # type: bool
                 content_type=None,     # type: Optional[str]
                 headers=None,          # type: Optional[AnyHeadersType]
                 cookies=None,          # type: Optional[AnyCookiesType]
                 **kwargs               # type: Any
                 ):                     # type: (...) -> AnyResponseType
    """
    Calls the request using either a :class:`webtest.TestApp` instance or :class:`requests.Request` from a string URL.

    Keyword arguments :paramref:`json`, :paramref:`data` and :paramref:`body` are all looked for to obtain the data.

    Header ``Content-Type`` is set with respect to explicit :paramref:`json` or via provided :paramref:`headers` when
    available. Explicit :paramref:`content_type` can also be provided to override all of these.

    Request cookies are set according to :paramref:`cookies`, or can be interpreted from ``Set-Cookie`` header.

    .. warning::
        When using :class:`TestApp`, some internal cookies can be stored from previous requests to retain the active
        user. Make sure to provide new set of cookies (or logout user explicitly) if different session must be used,
        otherwise they will be picked up automatically. For 'empty' cookies, provide an empty dictionary.

    :param test_item: one of `BaseTestCase`, `webtest.TestApp` or remote server URL to call with `requests`
    :param method: request method (GET, POST, PATCH, PUT, DELETE)
    :param path: test path starting at base path that will be appended to the application's endpoint.
    :param params: query parameters added to the request path.
    :param json: explicit JSON body content to use as request body.
    :param data: body content string to use as request body, can be JSON if matching ``Content-Type`` is identified.
    :param body: alias to :paramref:`data`.
    :param content_type:
        Enforce specific content-type of provided data body. Otherwise, attempt to retrieve it from request headers.
        Inferred JSON content-type when :paramref:`json` is employed, unless overridden explicitly.
    :param headers: Set of headers to send the request. Header ``Content-Type`` is looked for if not overridden.
    :param cookies: Cookies to provide to the request.
    :param timeout: passed down to :mod:`requests` when using URL, otherwise ignored (unsupported).
    :param retries: number of retry attempts in case the requested failed due to timeout (only when using URL).
    :param allow_redirects:
        Passed down to :mod:`requests` when using URL, handled manually for same behaviour when using :class:`TestApp`.
    :param kwargs: any additional keywords that will be forwarded to the request call.
    :returns: response of the request
    """
    method = method.upper()
    status = kwargs.pop("status", None)

    # obtain json body from any json/data/body kw and empty {} if not specified
    # reapply with the expected webtest/requests method kw afterward
    _body = json or data or body or {}

    app_or_url = get_app_or_url(test_item)
    if isinstance(app_or_url, TestApp):
        # set 'cookies' handled by the 'TestApp' instance if not present or different
        if cookies is not None:
            cookies = dict(cookies)  # convert tuple-list as needed
            if not app_or_url.cookies or app_or_url.cookies != cookies:
                app_or_url.cookies.update(cookies)

        # obtain Content-Type header if specified to ensure it is properly applied
        kwargs["content_type"] = content_type if content_type else get_header("Content-Type", headers)

        # update path with query parameters since TestApp does not have an explicit argument when not using GET
        if params:
            path += "?" + "&".join(f"{k!s}={v!s}" for k, v in params.items() if v is not None)

        kwargs.update({
            "params": _body,  # TestApp uses 'params' for the body during POST (these are not the query parameters)
            "headers": dict(headers or {}),  # adjust if none provided or specified as tuple list
        })
        # convert JSON body as required
        if _body is not None and (json is not None or kwargs["content_type"] == CONTENT_TYPE_JSON):
            kwargs["params"] = json_pkg.dumps(_body, cls=json_pkg.JSONEncoder)
            kwargs["content_type"] = CONTENT_TYPE_JSON  # enforce if only 'json' keyword provided
            kwargs["headers"]["Content-Length"] = str(len(kwargs["params"]))  # need to fix with override JSON payload
        if status and status >= 300:
            kwargs["expect_errors"] = True
        err_code = None
        err_msg = None
        try:
            resp = app_or_url._gen_request(method, path, **kwargs)  # pylint: disable=W0212  # noqa: W0212
        except AppError as exc:
            err_code = exc
            err_msg = str(exc)
        except HTTPException as exc:
            err_code = exc.status_code
            err_msg = str(exc) + str(getattr(exc, "exception", ""))
        except Exception as exc:
            err_code = 500
            err_msg = f"Unknown: {exc!s}"
        finally:
            if err_code:
                info = json_msg({"path": path, "method": method, "body": _body, "headers": kwargs["headers"]})
                result = "Request raised unexpected error: {!s}\nError: {}\nRequest:\n{}"
                raise AssertionError(result.format(err_code, err_msg, info))

        # automatically follow the redirect if any and evaluate its response
        max_redirect = kwargs.get("max_redirects", 5)
        while 300 <= resp.status_code < 400 and max_redirect > 0:  # noqa
            resp = resp.follow()
            max_redirect -= 1
        assert max_redirect >= 0, "Maximum follow redirects reached."
        # test status accordingly if specified
        assert resp.status_code == status or status is None, "Response not matching the expected status code."
        return resp

    kwargs.pop("expect_errors", None)  # remove keyword specific to TestApp
    content_type = get_header("Content-Type", headers)
    if json or content_type == CONTENT_TYPE_JSON:
        kwargs["json"] = _body
    elif data or body:
        kwargs["data"] = _body
    url = f"{app_or_url}{path}"
    while True:
        try:
            return requests.request(method, url, params=params, headers=headers, cookies=cookies,
                                    timeout=timeout, allow_redirects=allow_redirects, **kwargs)
        except requests.exceptions.ReadTimeout:
            if retries <= 0:
                raise
            retries -= 1


def visual_repr(item):
    # type: (Any) -> str
    try:
        if isinstance(item, (dict, list)):
            return json_pkg.dumps(item, indent=4, ensure_ascii=False)
    except Exception:  # noqa
        pass
    return f"'{repr(item)}'"


def format_test_val_ref(val, ref, pre="Fail", msg=None):
    if is_null(msg):
        _msg = f"({pre}) Failed condition between test and reference values."
    else:
        _msg = f"({pre}) Test value: {visual_repr(val)}, Reference value: {visual_repr(ref)}"
        if isinstance(msg, str):
            _msg = f"{msg}\n{_msg}"
    return _msg


def all_equal(iter_val, iter_ref, any_order=False):
    if not (hasattr(iter_val, "__iter__") and hasattr(iter_ref, "__iter__")):
        return False
    if len(iter_val) != len(iter_ref):
        return False
    if any_order:
        return all(it in iter_ref for it in iter_val)
    return all(it == ir for it, ir in zip(iter_val, iter_ref))


def check_all_equal(iter_val, iter_ref, msg=None, any_order=False):
    # type: (Collection[Any], Union[Collection[Any], NullType], Optional[str], bool) -> None
    """
    :param iter_val: tested values.
    :param iter_ref: reference values.
    :param msg: override message to display if failing test.
    :param any_order: allow equal values to be provided in any order, otherwise order must match as well as values.
    :raises AssertionError:
        If all values in :paramref:`iter_val` are not equal to values within :paramref:`iter_ref`.
        If :paramref:`any_order` is ``False``, also raises if equal items are not in the same order.
    """
    r_val = repr(iter_val)
    r_ref = repr(iter_ref)
    assert all_equal(iter_val, iter_ref, any_order), format_test_val_ref(r_val, r_ref, pre="All Equal Fail", msg=msg)


def check_val_equal(val, ref, msg=None):
    # type: (Any, Union[Any, NullType], Optional[str]) -> None
    """:raises AssertionError: if :paramref:`val` is not equal to :paramref:`ref`."""
    assert is_null(ref) or val == ref, format_test_val_ref(val, ref, pre="Equal Fail", msg=msg)


def check_val_not_equal(val, ref, msg=None):
    # type: (Any, Union[Any, NullType], Optional[str]) -> None
    """:raises AssertionError: if :paramref:`val` is equal to :paramref:`ref`."""
    assert is_null(ref) or val != ref, format_test_val_ref(val, ref, pre="Not Equal Fail", msg=msg)


def check_val_is_in(val, ref, msg=None):
    # type: (Any, Union[Any, NullType], Optional[str]) -> None
    """:raises AssertionError: if :paramref:`val` is not in to :paramref:`ref`."""
    assert is_null(ref) or val in ref, format_test_val_ref(val, ref, pre="Is In Fail", msg=msg)


def check_val_not_in(val, ref, msg=None):
    # type: (Any, Union[Any, NullType], Optional[str]) -> None
    """:raises AssertionError: if :paramref:`val` is in to :paramref:`ref`."""
    assert is_null(ref) or val not in ref, format_test_val_ref(val, ref, pre="Not In Fail", msg=msg)


def check_val_type(val, ref, msg=None):
    # type: (Any, Union[Type[Any], NullType, Iterable[Type[Any]]], Optional[str]) -> None
    """:raises AssertionError: if :paramref:`val` is not an instanced of :paramref:`ref`."""
    assert isinstance(val, ref), format_test_val_ref(val, repr(ref), pre="Type Fail", msg=msg)


def check_raises(func, exception_type, msg=None):
    # type: (Callable[[], Any], Type[Exception], Optional[str]) -> Exception
    """
    Calls the callable and verifies that the specific exception was raised.

    :raise AssertionError: on failing exception check or missing raised exception.
    :returns: raised exception of expected type if it was raised.
    """
    msg = f": {msg}" if msg else "."
    try:
        func()
    except Exception as exc:  # pylint: disable=W0703
        msg = f"Wrong exception [{type(exc).__name__!s}] raised instead of [{exception_type.__name__!s}]{msg}"
        assert isinstance(exc, exception_type), msg
        return exc
    raise AssertionError(f"Exception [{exception_type.__name__!s}] was not raised{msg}")


def check_no_raise(func, msg=None):
    # type: (Callable[[], Any], Optional[str]) -> Any
    """
    Calls the callable and verifies that no exception was raised.

    :raise AssertionError: on any raised exception.
    """
    try:
        return func()
    except Exception as exc:  # pylint: disable=W0703
        msg = f": {msg}" if msg else "."
        raise AssertionError(f"Exception [{type(exc).__name__!r}] was raised when none is expected{msg}")


def check_response_basic_info(response,                         # type: AnyResponseType
                              expected_code=200,                # type: int
                              expected_type=CONTENT_TYPE_JSON,  # type: str
                              expected_method="GET",            # type: str
                              extra_message=None,               # type: Optional[str]
                              ):                                # type: (...) -> Union[JSON, str]
    """
    Validates basic `Cowbird` API response metadata. For UI pages, employ :func:`check_ui_response_basic_info` instead.

    If the expected content-type is JSON, further validations are accomplished with specific metadata fields that are
    always expected in the response body. Otherwise, minimal validation of basic fields that can be validated regardless
    of content-type is done.

    :param response: response to validate.
    :param expected_code: status code to validate from the response.
    :param expected_type: Content-Type to validate from the response.
    :param expected_method: method 'GET', 'POST', etc. to validate from the response if an error.
    :param extra_message: additional message to append to every specific test message if provided.
    :returns: json body of the response for convenience.
    """
    def _(_msg):
        return _msg + " " + extra_message if extra_message else _msg

    check_val_is_in("Content-Type", dict(response.headers), msg=_("Response doesn't define 'Content-Type' header."))
    content_types = get_response_content_types_list(response)
    check_val_is_in(expected_type, content_types, msg=_("Response doesn't match expected HTTP Content-Type header."))
    code_message = "Response doesn't match expected HTTP status code."
    if expected_type == CONTENT_TYPE_JSON:
        # provide more details about mismatching code since to help debug cause of error
        code_message += f"\nReason:\n{json_msg(get_json_body(response))}"
    check_val_equal(response.status_code, expected_code, msg=_(code_message))

    if expected_type == CONTENT_TYPE_JSON:
        body = get_json_body(response)
        check_val_is_in("code", body, msg=_("Parameter 'code' should be in response JSON body."))
        check_val_is_in("type", body, msg=_("Parameter 'type' should be in response JSON body."))
        check_val_is_in("detail", body, msg=_("Parameter 'detail' should be in response JSON body."))
        check_val_equal(body["code"], expected_code, msg=_("Parameter 'code' should match HTTP status code."))
        check_val_equal(body["type"], expected_type, msg=_("Parameter 'type' should match HTTP Content-Type header."))
        check_val_not_equal(body["detail"], "", msg=_("Parameter 'detail' should not be empty."))
    else:
        body = response.text

    if response.status_code >= 400:
        # error details available for any content-type, just in different format
        check_val_is_in("url", body, msg=_("Request URL missing from contents,"))
        check_val_is_in("path", body, msg=_("Request path missing from contents."))
        check_val_is_in("method", body, msg=_("Request method missing from contents."))
        if expected_type == CONTENT_TYPE_JSON:  # explicitly check by dict-key if JSON
            check_val_equal(body["method"], expected_method, msg=_("Request method not matching expected value."))

    return body


def check_error_param_structure(body,                                   # type: JSON
                                param_value=null,                       # type: Optional[Any]
                                param_name=null,                        # type: Optional[str]
                                param_compare=null,                     # type: Optional[Any]
                                is_param_value_literal_unicode=False,   # type: bool
                                param_name_exists=False,                # type: bool
                                param_compare_exists=False,             # type: bool
                                ):                                      # type: (...) -> None
    """
    Validates error response ``param`` information based on different Cowbird version formats.

    :param body: JSON body of the response to validate.
    :param param_value:
        Expected 'value' of param the parameter.
        Contained field value not verified if ``null``, only presence of the field.
    :param param_name:
        Expected 'name' of param. Ignored for older Cowbird version that did not provide this information.
        Contained field value not verified if ``null`` and ``param_name_exists`` is ``True`` (only its presence).
        If provided, automatically implies ``param_name_exists=True``. Skipped otherwise.
    :param param_compare:
        Expected 'compare'/'param_compare' value (filed name according to version)
        Contained field value not verified if ``null`` and ``param_compare_exists`` is ``True`` (only its presence).
        If provided, automatically implies ``param_compare_exists=True``. Skipped otherwise.
    :param is_param_value_literal_unicode: param value is represented as `u'{paramValue}'` for older Cowbird version.
    :param param_name_exists: verify that 'name' is in the body, not validating its value.
    :param param_compare_exists: verify that 'compare'/'param_compare' is in the body, not validating its value.
    :raises AssertionError: on any failing condition
    """
    check_val_type(body, dict)
    check_val_is_in("param", body)
    check_val_type(body["param"], dict)
    check_val_is_in("value", body["param"])
    if param_name_exists or param_name is not null:
        check_val_is_in("name", body["param"])
        if param_name is not null:
            check_val_equal(body["param"]["name"], param_name)
    if param_value is not null:
        check_val_equal(body["param"]["value"], param_value)
    if param_compare_exists or param_compare is not null:
        check_val_is_in("compare", body["param"])
        if param_compare is not null:
            check_val_equal(body["param"]["compare"], param_compare)


def check_path_permissions(path, permissions):
    # type: (Union[str, os.PathLike], int) -> None
    """
    Checks if the path has the right permissions, by verifying the last digits of the octal permissions.
    """
    assert oct(os.stat(path)[ST_MODE] & 0o777) == oct(permissions & 0o777)


def check_mock_has_calls(mocked_fct, calls):
    mocked_fct.assert_has_calls(calls, any_order=True)
    mocked_fct.reset_mock()
