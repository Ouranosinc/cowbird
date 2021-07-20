#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import logging
import os
import sys
import types
import subprocess
import importlib
from configparser import ConfigParser
from enum import Enum
from inspect import isclass, isfunction
from typing import TYPE_CHECKING

from celery.app import Celery
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPClientError, HTTPException
from pyramid.registry import Registry
from pyramid.request import Request
from pyramid.response import Response
from pyramid.settings import truthy
from pyramid.threadlocal import get_current_registry
from pyramid_celery import celery_app as pyramid_celery_app
from requests.structures import CaseInsensitiveDict
from webob.headers import EnvironHeaders, ResponseHeaders

from cowbird import __meta__
from cowbird.constants import get_constant, validate_required

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from typing import _TC  # noqa: E0611,F401,W0212 # pylint: disable=E0611
    from typing import Any, List, NoReturn, Optional, Type, Union
    AnyRegistryContainer = Union[Configurator, Registry, Request, Celery]

    from pyramid.events import NewRequest

    from cowbird.typedefs import AnyHeadersType, AnyKey, AnyResponseType, AnySettingsContainer, SettingsType

CONTENT_TYPE_ANY = "*/*"
CONTENT_TYPE_JSON = "application/json"
CONTENT_TYPE_FORM = "application/x-www-form-urlencoded"
CONTENT_TYPE_HTML = "text/html"
CONTENT_TYPE_PLAIN = "text/plain"
CONTENT_TYPE_APP_XML = "application/xml"
CONTENT_TYPE_TXT_XML = "text/xml"
FORMAT_TYPE_MAPPING = {
    CONTENT_TYPE_JSON: CONTENT_TYPE_JSON,
    CONTENT_TYPE_HTML: CONTENT_TYPE_HTML,
    CONTENT_TYPE_PLAIN: CONTENT_TYPE_PLAIN,
    CONTENT_TYPE_APP_XML: CONTENT_TYPE_APP_XML,
    CONTENT_TYPE_TXT_XML: CONTENT_TYPE_TXT_XML,
    "json": CONTENT_TYPE_JSON,
    "html": CONTENT_TYPE_HTML,
    "text": CONTENT_TYPE_PLAIN,
    "plain": CONTENT_TYPE_PLAIN,
    "xml": CONTENT_TYPE_TXT_XML,
}
SUPPORTED_ACCEPT_TYPES = [
    CONTENT_TYPE_JSON, CONTENT_TYPE_HTML, CONTENT_TYPE_PLAIN, CONTENT_TYPE_APP_XML, CONTENT_TYPE_TXT_XML
]
SUPPORTED_FORMAT_TYPES = list(FORMAT_TYPE_MAPPING.keys())
KNOWN_CONTENT_TYPES = SUPPORTED_ACCEPT_TYPES + [CONTENT_TYPE_FORM, CONTENT_TYPE_ANY]

USE_CELERY_CFG = "use_celery"
USE_PYRAMID_CELERY_APP_CFG = "use_pyramid_celery_app"


def get_logger(name, level=None, force_stdout=None, message_format=None, datetime_format=None):
    # type: (str, Optional[int], bool, Optional[str], Optional[str]) -> logging.Logger
    """
    Immediately sets the logger level to avoid duplicate log outputs from the `root logger` and `this logger` when
    `level` is ``logging.NOTSET``.
    """
    logger = logging.getLogger(name)
    if logger.level == logging.NOTSET:
        # use package log level if it was specified via ini config with logger sections
        level = level or logging.getLogger(__meta__.__package__).getEffectiveLevel()
        if not level:
            # pylint: disable=C0415     # avoid circular import
            from cowbird.constants import COWBIRD_LOG_LEVEL
            level = COWBIRD_LOG_LEVEL
        logger.setLevel(level)
    if force_stdout or message_format or datetime_format:
        set_logger_config(logger, force_stdout, message_format, datetime_format)
    return logger


LOGGER = get_logger(__name__)


def set_logger_config(logger, force_stdout=False, message_format=None, datetime_format=None):
    # type: (logging.Logger, bool, Optional[str], Optional[str]) -> logging.Logger
    """
    Applies the provided logging configuration settings to the logger.
    """
    if not logger:
        return logger
    handler = None
    if force_stdout:
        all_handlers = logging.root.handlers + logger.handlers
        if not any(isinstance(h, logging.StreamHandler) for h in all_handlers):
            handler = logging.StreamHandler(sys.stdout)
            logger.addHandler(handler)  # noqa: type
    if not handler:
        if logger.handlers:
            handler = logger.handlers
        else:
            handler = logging.StreamHandler(sys.stdout)
            logger.addHandler(handler)
    if message_format or datetime_format:
        handler.setFormatter(logging.Formatter(fmt=message_format, datefmt=datetime_format))
    return logger


def print_log(msg, logger=None, level=logging.INFO, **kwargs):
    # type: (str, Optional[logging.Logger], int, Any) -> None
    """
    Logs the requested message to the logger and optionally enforce printing to the console according to configuration
    value defined by ``COWBIRD_LOG_PRINT``.
    """
    # pylint: disable=C0415     # cannot use 'get_constant', recursive call
    from cowbird.constants import COWBIRD_LOG_PRINT

    if not logger:
        logger = get_logger(__name__)
    if COWBIRD_LOG_PRINT:
        set_logger_config(logger, force_stdout=True)
    if logger.disabled:
        logger.disabled = False
    logger.log(level, msg, **kwargs)


def raise_log(msg, exception=Exception, logger=None, level=logging.ERROR):
    # type: (str, Type[Exception], Optional[logging.Logger], int) -> NoReturn
    """
    Logs the provided message to the logger and raises the corresponding exception afterwards.

    :raises exception: whichever exception provided is raised systematically after logging.
    """
    if not logger:
        logger = get_logger(__name__)
    logger.log(level, msg)
    if not isclass(exception) or not issubclass(exception, Exception):
        exception = Exception
    raise exception(msg)


def bool2str(value):
    # type: (Any) -> str
    """
    Converts :paramref:`value` to explicit ``"true"`` or ``"false"`` :class:`str` with permissive variants comparison
    that can represent common falsy or truthy values.
    """
    return "true" if str(value).lower() in truthy else "false"


def islambda(func):
    # type: (Any) -> bool
    """
    Evaluate if argument is a callable :class:`lambda` expression.
    """
    return isinstance(func, types.LambdaType) and func.__name__ == (lambda: None).__name__  # noqa


def configure_celery(config, config_ini):
    logger = get_logger(__name__)
    logger.info("Configuring celery")

    # shared_tasks use the default celery app by default so setting the pyramid_celery celery_app as default prevent
    # celery to create its own app instance (which is not configured properly and is bugging the shared tasks).
    # Also it must be done early because as soon as config scan is started, some packages may include celery and
    # and it will create its own app instance.
    if config.registry.settings.get(USE_PYRAMID_CELERY_APP_CFG, True):
        pyramid_celery_app.set_default()

    # Add the config dir in path so that celeryconfig file can be found
    sys.path.append(os.path.dirname(config_ini))
    config.include("pyramid_celery")
    config.configure_celery(config_ini)

    logger.info("Locating celery tasks...")
    grep_command = ["grep", "--include=*.py", "-rw", os.path.dirname(__file__), "-e", "^@shared_task"]
    task_files = subprocess.run(grep_command, stdout=subprocess.PIPE, text=True)
    install_dir = os.path.dirname(os.path.dirname(__file__))
    modules_set = set()
    for file in task_files.stdout.strip("\n").split("\n"):
        if not file:
            continue
        # Python file relative to package install directory
        rel_name = os.path.relpath(file.split(":")[0], install_dir)
        # Get the module name by striping the extension .py and replacing / by .
        mod_name = rel_name[:-3].replace("/", ".")
        modules_set.add(mod_name)
    for module in modules_set:
        importlib.import_module(module)
        logger.info("Importing celery tasks from module [%s]", module)


def get_app_config(container):
    # type: (AnySettingsContainer, bool) -> Configurator
    """
    Generates application configuration with all required utilities and settings configured.
    """
    import cowbird.constants  # pylint: disable=C0415  # to override specific constants/variables

    logger = get_logger(__name__)

    # override INI config path if provided with --paste to gunicorn, otherwise use environment variable
    config_settings = get_settings(container)
    config_env = get_constant("COWBIRD_INI_FILE_PATH", config_settings, raise_missing=True)
    config_ini = (container or {}).get("__file__", config_env)
    logger.info("Using initialisation file : [%s]", config_ini)
    if config_ini != config_env:
        cowbird.constants.COWBIRD_INI_FILE_PATH = config_ini
        config_settings["cowbird.ini_file_path"] = config_ini
        logger.info("Environment variable COWBIRD_INI_FILE_PATH [%s] ignored", config_env)
    settings = get_settings_from_config_ini(config_ini)
    settings.update(config_settings)

    print_log("Setting up loggers...", LOGGER)
    log_lvl = get_constant("COWBIRD_LOG_LEVEL", settings, "cowbird.log_level", default_value="INFO",
                           raise_missing=False, raise_not_set=False, print_missing=True)
    # apply proper value in case it was in ini AND env since up until then, only env was check
    # we want to prioritize the ini definition
    cowbird.constants.COWBIRD_LOG_LEVEL = log_lvl
    LOGGER.setLevel(log_lvl)

    print_log("Validate settings that require explicit definitions...", LOGGER)
    validate_required(settings)

    # avoid cornice conflicting with pyramid exception views
    settings["handle_exceptions"] = False

    # create configurator or use one defined as input to preserve previous setup/include/etc.
    config = Configurator() if not isinstance(container, Configurator) else container
    config.setup_registry(settings=settings)

    # Must be done before include scan, see configure_celery for more details
    if settings.get(USE_CELERY_CFG, True):
        configure_celery(config, config_ini)

    # don't use scan otherwise modules like 'cowbird.adapter' are
    # automatically found and cause import errors on missing packages
    print_log("Including Cowbird modules...", LOGGER)
    config.include("pyramid_mako")
    config.include("cowbird")
    # NOTE: don't call 'config.scan("cowbird")' to avoid parsing issues with colander/cornice,
    #       add them explicitly with 'config.include(<module>)', and then they can do 'config.scan()'

    return config


def get_settings_from_config_ini(config_ini_path, section=None):
    """
    Loads configuration INI settings with additional handling.
    """
    parser = ConfigParser()
    parser.optionxform = lambda option: option  # preserve case of config (default applies lowercase)
    result = parser.read([config_ini_path])
    # raise silently ignored missing file
    if len(result) != 1 or not os.path.isfile(result[0]):
        if result:
            result = result[0] or os.path.abspath(str(config_ini_path))  # in case not found, use expected location
            message = "Cannot find INI configuration file [{}] resolved as [{}]".format(config_ini_path, result)
        else:
            message = "Cannot find INI configuration file [{}]".format(config_ini_path)
        raise ValueError(message)
    if section is None:
        section = "app:{}_app".format(__meta__.__package__)
    return dict(parser.items(section=section))


def get_registry(container, nothrow=False):
    # type: (AnyRegistryContainer, bool) -> Optional[Registry]
    """
    Retrieves the application ``registry`` from various containers referencing to it.
    """
    if isinstance(container, Celery):
        return container.conf.get("PYRAMID_REGISTRY", {})
    if isinstance(container, (Configurator, Request)):
        return container.registry
    if isinstance(container, Registry):
        return container
    if nothrow:
        return None
    raise TypeError("Could not retrieve registry from container object of type [{}].".format(type(container)))


def get_json(response):
    """
    Retrieves the 'JSON' body of a response using the property/callable according to the response's implementation.
    """
    if isinstance(response.json, dict):
        return response.json
    return response.json()


def get_header(header_name, header_container, default=None, split=None):
    # type: (str, AnyHeadersType, Optional[str], Optional[Union[str, List[str]]]) -> Optional[str]
    """
    Retrieves ``header_name`` by fuzzy match (independently of upper/lower-case and underscore/dash) from various
    framework implementations of ``Headers``.

    If ``split`` is specified, the matched ``header_name`` is first split with it and the first item is returned.
    This allows to parse complex headers (e.g.: ``text/plain; charset=UTF-8`` to ``text/plain`` with ``split=';'``).

    :param header_name: header to find.
    :param header_container: where to look for `header_name`.
    :param default: value to returned if `header_container` is invalid or `header_name` could not be found.
    :param split: character(s) to use to split the *found* `header_name`.
    """
    def fuzzy_name(name):
        return name.lower().replace("-", "_")

    if header_container is None:
        return default
    headers = header_container
    if isinstance(headers, (ResponseHeaders, EnvironHeaders, CaseInsensitiveDict)):
        headers = dict(headers)
    if isinstance(headers, dict):
        headers = header_container.items()
    header_name = fuzzy_name(header_name)
    for h, v in headers:
        if fuzzy_name(h) == header_name:
            if isinstance(split, str) and len(split) > 1:
                split = [c for c in split]
            if hasattr(split, "__iter__") and not isinstance(split, str):
                for sep in split:
                    v = v.replace(sep, split[0])
                split = split[0]
            return (v.split(split)[0] if split else v).strip()
    return default


def convert_response(response):
    # type: (AnyResponseType) -> Response
    """
    Converts a :class:`requests.Response` object to an equivalent :class:`pyramid.response.Response` object.

    Content of the :paramref:`response` is expected to be JSON.

    :param response: response to be converted
    :returns: converted response
    """
    if isinstance(response, Response):
        return response
    json_body = get_json(response)
    pyramid_response = Response(body=json_body, headers=response.headers)
    if hasattr(response, "cookies"):
        for cookie in response.cookies:
            pyramid_response.set_cookie(name=cookie.name, value=cookie.value, overwrite=True)  # noqa
    if isinstance(response, HTTPException):
        for header_name, header_value in response.headers._items:  # noqa # pylint: disable=W0212
            if header_name.lower() == "set-cookie":
                pyramid_response.set_cookie(name=header_name, value=header_value, overwrite=True)
    return pyramid_response


def get_settings(container, app=False):
    # type: (Optional[AnySettingsContainer], bool) -> SettingsType
    """
    Retrieve application settings from a supported container.

    :param container: supported container with an handle to application settings.
    :param app: allow retrieving from current thread registry if no container was defined.
    :return: found application settings dictionary.
    :raise TypeError: when no application settings could be found or unsupported container.
    """
    if isinstance(container, (Configurator, Request)):
        return container.registry.settings  # noqa
    if isinstance(container, Registry):
        return container.settings
    if isinstance(container, dict):
        return container
    if container is None and app:
        print_log("Using settings from local thread.", level=logging.DEBUG)
        registry = get_current_registry()
        return registry.settings
    raise TypeError("Could not retrieve settings from container object [{}]".format(type(container)))


def fully_qualified_name(obj):
    # type: (Union[Any, Type[Any]]) -> str
    """
    Obtains the ``'<module>.<name>'`` full path definition of the object to allow finding and importing it.
    """
    cls = obj if isclass(obj) or isfunction(obj) else type(obj)
    return ".".join([obj.__module__, cls.__name__])


def log_request_format(request):
    # type: (Request) -> str
    return "{!s} {!s} {!s}".format(request.method, request.host, request.path)


def log_request(event):
    # type: (NewRequest) -> None
    """
    Subscriber event that logs basic details about the incoming requests.
    """
    request = event.request  # type: Request
    LOGGER.info("Request: [%s]", log_request_format(request))
    if LOGGER.isEnabledFor(logging.DEBUG):
        def items_str(items):
            return "\n  ".join(["{!s}: {!s}".format(h, items[h]) for h in items]) if len(items) else "-"

        header_str = items_str(request.headers)
        params_str = items_str(request.params)
        body_str = str(request.body) or "-"
        LOGGER.debug("Request details:\n"
                     "URL: %s\n"
                     "Path: %s\n"
                     "Method: %s\n"
                     "Headers:\n"
                     "  %s\n"
                     "Parameters:\n"
                     "  %s\n"
                     "Body:\n"
                     "  %s",
                     request.url, request.path, request.method, header_str, params_str, body_str)


def log_exception_tween(handler, registry):  # noqa: F811
    """
    Tween factory that logs any exception before re-raising it.

    Application errors are marked as ``ERROR`` while non critical HTTP errors are marked as ``WARNING``.
    """
    def log_exc(request):
        try:
            return handler(request)
        except Exception as err:
            lvl = logging.ERROR
            exc = True
            if isinstance(err, HTTPClientError):
                lvl = logging.WARNING
                exc = False
            LOGGER.log(lvl, "Exception during request: [%s]", log_request_format(request), exc_info=exc)
            raise err
    return log_exc


def is_json_body(body):
    # type: (Any) -> bool
    if not body:
        return False
    try:
        json.loads(body)
    except (ValueError, TypeError):
        return False
    return True


# note: must not define any enum value here to allow inheritance by subclasses
class ExtendedEnum(Enum):
    """
    Utility :class:`enum.Enum` methods.

    Create an extended enum with these utilities as follows::

        class CustomEnum(ExtendedEnum):
            ItemA = "A"
            ItemB = "B"
    """

    @classmethod
    def names(cls):
        # type: () -> List[str]
        """
        Returns the member names assigned to corresponding enum elements.
        """
        return list(cls.__members__)

    @classmethod
    def values(cls):
        # type: () -> List[AnyKey]
        """
        Returns the literal values assigned to corresponding enum elements.
        """
        return [m.value for m in cls.__members__.values()]                      # pylint: disable=E1101

    @classmethod
    def get(cls, key_or_value, default=None):
        # type: (AnyKey, Optional[Any]) -> Optional[_TC]
        """
        Finds an enum entry by defined name or its value.

        Returns the entry directly if it is already a valid enum.
        """
        # Python 3.8 disallow direct check of 'str' in 'enum'
        members = [member for member in cls]
        if key_or_value in members:                                             # pylint: disable=E1133
            return key_or_value
        for m_key, m_val in cls.__members__.items():                            # pylint: disable=E1101
            if key_or_value == m_key or key_or_value == m_val.value:            # pylint: disable=R1714
                return m_val
        return default


# taken from https://stackoverflow.com/questions/6760685/creating-a-singleton-in-python
class SingletonMeta(type):
    """
    A metaclass that creates a Singleton base class when called.

    Create a class such that.

    .. code-block:: python

        class A(object, metaclass=SingletonMeta):
            pass

        class B(object, metaclass=SingletonMeta):
            pass

        a1 = A()
        a2 = A()
        b1 = B()
        b2 = B()
        a1 is a2    # True
        b1 is b2    # True
        a1 is b1    # False
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(SingletonMeta, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class NullType(object, metaclass=SingletonMeta):
    """
    Represents a null value to differentiate from None.
    """

    def __repr__(self):
        return "<null>"

    @staticmethod
    def __nonzero__():
        return False

    __bool__ = __nonzero__
    __len__ = __nonzero__


null = NullType()  # pylint: disable=C0103,invalid-name


def is_null(item):
    return isinstance(item, NullType) or item is null


def get_config_path():
    settings = get_settings(None, app=True)
    return get_constant("COWBIRD_CONFIG_PATH", settings,
                        default_value=None,
                        raise_missing=False, raise_not_set=False,
                        print_missing=True)
