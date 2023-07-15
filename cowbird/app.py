#!/usr/bin/env python
# coding: utf-8
"""
Cowbird is a middleware that manages interactions between various birds of the bird-house stack.
"""
import sys
from typing import Optional

from pyramid.router import Router

from cowbird.config import (
    get_all_configs,
    validate_handlers_config_schema,
    validate_sync_config,
    validate_sync_perm_config_schema
)
from cowbird.monitoring.monitoring import Monitoring
from cowbird.typedefs import SettingsType, SettingValue
from cowbird.utils import get_app_config, get_config_path, get_logger, print_log

LOGGER = get_logger(__name__)


def get_app(global_config: Optional[SettingsType] = None, **settings: SettingValue) -> Router:
    """
    This function returns the Pyramid WSGI application.

    It can also be used for test purpose (some config needed only in pyramid and not in tests are still in the main)
    """
    global_config = global_config or {}
    global_config.update(settings)
    config = get_app_config(global_config)
    config_path = get_config_path()
    LOGGER.info("Using configuration file: [%s]", config_path)

    handlers_cfgs = get_all_configs(config_path, "handlers", allow_missing=True)
    for handlers_cfg in handlers_cfgs:
        validate_handlers_config_schema(handlers_cfg)
    if not handlers_cfgs:
        LOGGER.warning("No handlers configuration found in [%s]", config_path)

    sync_perm_cfgs = get_all_configs(config_path, "sync_permissions", allow_missing=True)
    # Validate sync_permissions config before starting the app
    for sync_perm_config in sync_perm_cfgs:
        validate_sync_perm_config_schema(sync_perm_config)
        for sync_cfg in sync_perm_config.values():
            validate_sync_config(sync_cfg)
    if not sync_perm_cfgs:
        LOGGER.warning("No permission mapping configuration found in [%s]", config_path)

    print_log("Starting Cowbird app...", LOGGER)
    wsgi_app = config.make_wsgi_app()

    # The main app is doing the monitoring
    if not sys.argv[0].endswith("celery"):
        # TODO: The monitoring should be done in a single worker to avoid picking an event multiple time
        Monitoring(config).start()

    return wsgi_app


def main(global_config: Optional[SettingsType] = None, **settings: SettingValue) -> Router:
    """
    This function returns the Pyramid WSGI application.
    """
    return get_app(global_config, **settings)


if __name__ == "__main__":
    main()
