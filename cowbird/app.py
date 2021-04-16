#!/usr/bin/env python
# coding: utf-8

"""
Cowbird is a service for AuthN and AuthZ based on Ziggurat-Foundations.
"""
from cowbird.utils import get_app_config, get_logger, print_log
from cowbird.monitoring.monitoring import Monitoring

LOGGER = get_logger(__name__)


def main(global_config=None, **settings):  # noqa: F811
    """
    This function returns the Pyramid WSGI application.
    """
    global_config = global_config or {}
    global_config.update(settings)
    config = get_app_config(global_config)

    Monitoring().start()

    print_log("Starting Cowbird app...", LOGGER)
    wsgi_app = config.make_wsgi_app()
    return wsgi_app


if __name__ == "__main__":
    main()
