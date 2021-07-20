#!/usr/bin/env python
# coding: utf-8

"""
Cowbird is a service for AuthN and AuthZ based on Ziggurat-Foundations.
"""
import sys

from cowbird.monitoring.monitoring import Monitoring
from cowbird.utils import get_app_config, get_logger, print_log

LOGGER = get_logger(__name__)


def get_app(global_config=None, **settings):
    """
    This function returns the Pyramid WSGI application.

    It can also be used for test purpose (some config needed only in pyramid and not in tests are still in the main)
    """
    global_config = global_config or {}
    global_config.update(settings)
    config = get_app_config(global_config)

    print_log("Starting Cowbird app...", LOGGER)
    wsgi_app = config.make_wsgi_app()

    # The main app is doing the monitoring
    if not sys.argv[0].endswith("celery"):
        # TODO: The monitoring should be done in a single worker to avoid picking an event multiple time
        Monitoring(config).start()

    return wsgi_app


def main(global_config=None, **settings):  # noqa: F811
    """
    This function returns the Pyramid WSGI application.
    """
    return get_app(global_config, **settings)


if __name__ == "__main__":
    main()
