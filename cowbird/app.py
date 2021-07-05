#!/usr/bin/env python
# coding: utf-8

"""
Cowbird is a service for AuthN and AuthZ based on Ziggurat-Foundations.
"""
from pyramid_celery import celery_app as app

from cowbird.monitoring.monitoring import Monitoring
# TODO: This is required by the celery worker to discover tasks,
#       we should add something like the celery autodiscover_tasks
from cowbird.services.impl import geoserver  # noqa # pylint: disable=unused-import

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

    Monitoring().start()

    print_log("Starting Cowbird app...", LOGGER)
    wsgi_app = config.make_wsgi_app()
    return wsgi_app


def main(global_config=None, **settings):  # noqa: F811
    """
    This function returns the Pyramid WSGI application.
    """
    # shared_tasks use the default celery app by default so setting the pyramid_celery celery_app as default prevent
    # celery to create its own app instance (which is not configured properly) and bugging the shared tasks
    # Also it must be done early because as soon as get_app_config is called celery create its own app instance
    app.set_default()

    return get_app(global_config, **settings)


if __name__ == "__main__":
    main()
