#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Constant settings for Cowbird application.

Constants defined with format ``COWBIRD_[VARIABLE_NAME]`` can be matched with corresponding
settings formatted as ``cowbird.[variable_name]`` in the ``cowbird.ini`` configuration file.

.. note::
    Since the ``cowbird.ini`` file has to be loaded by the application to retrieve various configuration settings,
    constant ``COWBIRD_INI_FILE_PATH`` (or any other `path variable` defined before it - see below) has to be defined
    by environment variable if the default location is not desired (ie: if you want to provide your own configuration).
"""
import logging
import os
import re
from typing import Optional
from typing_extensions import Literal

from pyramid.settings import asbool
from pyramid.threadlocal import get_current_registry

from cowbird.typedefs import AnySettingsContainer, SettingValue

AnyLogLevel = Literal[
    "NOTSET", 0,
    "DEBUG", "debug", 10,
    "INFO", "info", 20,
    "WARNING", "warning", 30,
    "ERROR", "error", 40,
    "FATAL", "fatal", 50,
    "CRITICAL", "critical", 50,
]

# ===========================
# path variables
# ===========================
COWBIRD_MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
COWBIRD_ROOT = os.path.dirname(COWBIRD_MODULE_DIR)
COWBIRD_CONFIG_DIR = os.getenv(
    "COWBIRD_CONFIG_DIR", os.path.join(COWBIRD_ROOT, "config"))
COWBIRD_CONFIG_PATH = os.getenv("COWBIRD_CONFIG_PATH")  # default None, require explicit specification
COWBIRD_INI_FILE_PATH = os.getenv(
    "COWBIRD_INI_FILE_PATH", f"{COWBIRD_CONFIG_DIR}/cowbird.ini")

# UID/GID used in birdhouse. We should assign the user's resources to this owner, so that the resources can be
# accessible to the user via JupyterHub.
DEFAULT_USER_UID = int(os.getenv("COWBIRD_FILESYSTEM_USER_UID", 1000))
DEFAULT_USER_GID = int(os.getenv("COWBIRD_FILESYSTEM_USER_GID", 1000))

DEFAULT_ADMIN_UID = int(os.getenv("COWBIRD_FILESYSTEM_ADMIN_UID", 0))
DEFAULT_ADMIN_GID = int(os.getenv("COWBIRD_FILESYSTEM_ADMIN_GID", 0))


def _get_default_log_level() -> AnyLogLevel:
    """
    Get logging level from INI configuration file or fallback to default ``INFO`` if it cannot be retrieved.
    """
    _default_log_lvl = "INFO"
    try:
        from cowbird.utils import get_settings_from_config_ini  # pylint: disable=C0415  # avoid circular import error
        _settings = get_settings_from_config_ini(COWBIRD_INI_FILE_PATH, section="logger_cowbird")
        _default_log_lvl = _settings.get("level", _default_log_lvl)
    # also considers 'ModuleNotFoundError' derived from 'ImportError', but not added to avoid Python <3.6 name error
    except (AttributeError, ImportError):  # noqa: W0703 # nosec: B110
        pass
    return _default_log_lvl


# ===========================
# variables from cowbird.env
# ===========================

# ---------------------------
# COWBIRD
# ---------------------------

COWBIRD_URL = os.getenv("COWBIRD_URL", None)    # must be defined
COWBIRD_LOG_LEVEL = os.getenv("COWBIRD_LOG_LEVEL", _get_default_log_level())      # log level to apply to the loggers
COWBIRD_LOG_PRINT = asbool(os.getenv("COWBIRD_LOG_PRINT", False))                 # log also forces print to the console
COWBIRD_LOG_REQUEST = asbool(os.getenv("COWBIRD_LOG_REQUEST", True))              # log detail of every incoming request
COWBIRD_LOG_EXCEPTION = asbool(os.getenv("COWBIRD_LOG_EXCEPTION", True))          # log detail of generated exceptions
COWBIRD_ADMIN_PERMISSION = "admin"

# ===========================
# constants
# ===========================

# ignore matches of settings and environment variables for following cases
COWBIRD_CONSTANTS = [
    "COWBIRD_CONSTANTS",
    "COWBIRD_MODULE_DIR",
    "COWBIRD_ROOT",
    "COWBIRD_ADMIN_PERMISSION",
    # add more as needed
]

# ===========================
# utilities
# ===========================

_REGEX_ASCII_ONLY = re.compile(r"\W|^(?=\d)")
_SETTING_SECTION_PREFIXES = [
    "cowbird",
]
_SETTINGS_REQUIRED = [
    "COWBIRD_URL",
    "COWBIRD_CONFIG_PATH",
    # FIXME: add others here as needed
]


def get_constant_setting_name(name: str) -> str:
    """
    Find the equivalent setting name of the provided environment variable name.

    Lower-case name and replace all non-ascii chars by `_`.
    Then, convert known prefixes with their dotted name.
    """
    name = re.sub(_REGEX_ASCII_ONLY, "_", name.strip().lower())
    for prefix in _SETTING_SECTION_PREFIXES:
        known_prefix = f"{prefix}_"
        dotted_prefix = f"{prefix}."
        if name.startswith(known_prefix):
            return name.replace(known_prefix, dotted_prefix, 1)
    return name


def get_constant(constant_name: str,
                 settings_container: Optional[AnySettingsContainer] = None,
                 settings_name: Optional[str] = None,
                 default_value: Optional[SettingValue] = None,
                 raise_missing: bool = True,
                 print_missing: bool = False,
                 raise_not_set: bool = True
                 ) -> SettingValue:
    """
    Search in order for matched value of :paramref:`constant_name`:
      1. search in :py:data:`COWBIRD_CONSTANTS`
      2. search in settings if specified
      3. search alternative setting names (see below)
      4. search in :mod:`cowbird.constants` definitions
      5. search in environment variables

    Parameter :paramref:`constant_name` is expected to have the format ``COWBIRD_[VARIABLE_NAME]`` although any value
    can be passed to retrieve generic settings from all above mentioned search locations.

    If :paramref:`settings_name` is provided as alternative name, it is used as is to search for results if
    :paramref:`constant_name` was not found. Otherwise, ``cowbird.[variable_name]`` is used for additional search when
    the format ``COWBIRD_[VARIABLE_NAME]`` was used for :paramref:`constant_name`
    (i.e.: ``COWBIRD_ADMIN_USER`` will also search for ``cowbird.admin_user`` and so on for corresponding constants).

    :param constant_name: key to search for a value
    :param settings_container: WSGI application settings container (if not provided, uses found one in current thread)
    :param settings_name: alternative name for `settings` if specified
    :param default_value: default value to be returned if not found anywhere, and exception raises are disabled.
    :param raise_missing: raise exception if key is not found anywhere
    :param print_missing: print message if key is not found anywhere, return ``None``
    :param raise_not_set: raise an exception if the found key is ``None``, search until last case if others are ``None``
    :returns: found value or `default_value`
    :raises ValueError: if resulting value is invalid based on options (by default raise missing/``None`` value)
    :raises LookupError: if no appropriate value could be found from all search locations (according to options)
    """
    from cowbird.utils import get_settings, print_log, raise_log  # pylint: disable=C0415  # avoid circular import error

    if constant_name in COWBIRD_CONSTANTS:
        return globals()[constant_name]
    missing = True
    cowbird_value = None
    if settings_container:
        settings = get_settings(settings_container)
    else:
        # note: this will work only after include of cowbird will have triggered configurator setup
        print_log("Using settings from local thread.", level=logging.DEBUG)
        settings = get_settings(get_current_registry())
    if settings and constant_name in settings:  # pylint: disable=E1135
        missing = False
        cowbird_value = settings.get(constant_name)
        if cowbird_value is not None:
            print_log(f"Constant found in settings with: {constant_name}", level=logging.DEBUG)
            return cowbird_value
    if not settings_name:
        settings_name = get_constant_setting_name(constant_name)
        print_log(f"Constant alternate search: {settings_name}", level=logging.DEBUG)
    if settings and settings_name and settings_name in settings:  # pylint: disable=E1135
        missing = False
        cowbird_value = settings.get(settings_name)
        if cowbird_value is not None:
            print_log(f"Constant found in settings with: {settings_name}", level=logging.DEBUG)
            return cowbird_value
    cowbird_globals = globals()
    if constant_name in cowbird_globals:
        missing = False
        cowbird_value = cowbird_globals.get(constant_name)
        if cowbird_value is not None:
            print_log(f"Constant found in definitions with: {constant_name}", level=logging.DEBUG)
            return cowbird_value
    if constant_name in os.environ:
        missing = False
        cowbird_value = os.environ.get(constant_name)
        if cowbird_value is not None:
            print_log(f"Constant found in environment with: {constant_name}", level=logging.DEBUG)
            return cowbird_value
    if not missing and raise_not_set:
        raise_log(f"Constant was found but was not set: {constant_name}",
                  level=logging.ERROR, exception=ValueError)
    if missing and raise_missing:
        raise_log(f"Constant could not be found: {constant_name}",
                  level=logging.ERROR, exception=LookupError)
    if missing and print_missing:
        print_log(f"Constant could not be found: {constant_name} (using default: {default_value})", level=logging.WARN)
    return cowbird_value or default_value


def validate_required(container: AnySettingsContainer) -> None:
    """
    Validates that some value is provided for every mandatory configuration setting.

    :raises: when any of the requirements are missing a definition.
    """
    for cfg in _SETTINGS_REQUIRED:
        get_constant(cfg, settings_container=container, raise_missing=True, raise_not_set=True)
