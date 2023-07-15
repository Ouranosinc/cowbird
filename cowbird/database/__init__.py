"""
Database package for pyramid.

Add the database in the pyramid registry and a property db for the requests.
"""

import logging
from typing import cast

from pyramid.config import Configurator
from pyramid.registry import Registry
from pyramid.request import Request
from pyramid.settings import asbool

from cowbird.database.mongodb import MongoDatabase
from cowbird.typedefs import AnySettingsContainer
from cowbird.utils import get_registry, get_settings

LOGGER = logging.getLogger(__name__)


def get_db(container: AnySettingsContainer, reset_connection: bool = False) -> MongoDatabase:
    """
    Obtains the database connection from configured application settings.

    If :paramref:`reset_connection` is ``True``, the :paramref:`container` must be the application :class:`Registry` or
    any container that can retrieve it to accomplish reference reset. Otherwise, any settings container can be provided.
    """
    registry = get_registry(container, nothrow=True)
    if not reset_connection and registry and isinstance(getattr(registry, "db", None), MongoDatabase):
        return registry.db
    database = MongoDatabase(container)
    if reset_connection:
        registry = get_registry(container)
        registry.db = database
    return database


def includeme(config: Configurator) -> None:
    settings = get_settings(config)
    if asbool(settings.get("cowbird.build_docs", False)):
        LOGGER.info("Skipping database when building docs...")
        return

    LOGGER.info("Adding database...")

    def _add_db(request: Request) -> MongoDatabase:
        return MongoDatabase(cast(Registry, request.registry))

    config.add_request_method(_add_db, "db", reify=True)
