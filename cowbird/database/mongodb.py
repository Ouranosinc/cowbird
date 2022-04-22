# MongoDB
# http://docs.pylonsproject.org/projects/pyramid-cookbook/en/latest/database/mongodb.html
import warnings
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import pymongo

from cowbird.database.base import DatabaseInterface
from cowbird.database.stores import MonitoringStore
from cowbird.utils import get_settings

# pylint: disable=C0103,invalid-name
MongoDB = None  # type: Optional[Database]
MongodbStores = frozenset([
    MonitoringStore,
])

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from typing import Any, Optional, Type, Union

    from pymongo.database import Database

    from cowbird.database.base import StoreSelector
    from cowbird.database.stores import StoreInterface
    from cowbird.typedefs import JSON, AnySettingsContainer

    AnyMongodbStore = Union[MongodbStores]
    AnyMongodbStoreType = Union[
        StoreSelector,
        AnyMongodbStore,
        Type[MonitoringStore],
    ]


class MongoDatabase(DatabaseInterface):
    _database = None
    _settings = None
    _stores = None
    type = "mongodb"

    def __init__(self, container):
        # type: (AnySettingsContainer) -> None
        """
        Initialize the mongo database from various type of container.
        """
        super(MongoDatabase, self).__init__(container)
        self._database = get_mongodb_engine(container)
        self._settings = get_settings(container)
        self._stores = {}

    def reset_store(self, store_type):
        store_type = self._get_store_type(store_type)
        return self._stores.pop(store_type, None)

    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (Union[str, Type[StoreInterface], AnyMongodbStoreType], *Any, **Any) -> AnyMongodbStore
        """
        Retrieve a store from the database.

        :param store_type: type of the store to retrieve/create.
        :param store_args: additional arguments to pass down to the store.
        :param store_kwargs: additional keyword arguments to pass down to the store.
        """
        store_type = self._get_store_type(store_type)

        for store in MongodbStores:
            if store.type == store_type:
                if store_type not in self._stores:
                    if "settings" not in store_kwargs:
                        store_kwargs["settings"] = self._settings
                    self._stores[store_type] = store(
                        collection=getattr(self.get_session(), store_type),
                        *store_args, **store_kwargs
                    )
                return self._stores[store_type]
        raise NotImplementedError(f"Database '{self.type}' cannot find matching store '{store_type}'.")

    def get_session(self):
        # type: (...) -> Any
        return self._database

    def get_information(self):
        # type: (...) -> JSON
        """
        :returns: {'version': version, 'type': db_type}
        """
        result = list(self._database.version.find().limit(1))[0]
        db_version = result["version_num"]
        return {"version": db_version, "type": self.type}

    def is_ready(self):
        # type: (...) -> bool
        return self._database is not None and self._settings is not None


def get_mongodb_connection(container):
    # type: (AnySettingsContainer) -> Database
    """
    Obtains the basic database connection from settings.
    """

    settings = get_settings(container)
    default_mongo_uri = "mongodb://0.0.0.0:27017/cowbird"
    if settings.get("mongo_uri", None) is None:
        warnings.warn(f"Setting 'mongo_uri' not defined in registry, using default [{default_mongo_uri}].")
        settings["mongo_uri"] = default_mongo_uri
    db_url = urlparse(settings["mongo_uri"])
    client = pymongo.MongoClient(
        host=db_url.hostname,
        port=db_url.port,
    )
    db = client[db_url.path[1:]]
    if db_url.username and db_url.password:
        db.authenticate(db_url.username, db_url.password)
    return db


def get_mongodb_engine(container):
    # type: (AnySettingsContainer) -> Database
    """
    Obtains the database with configuration ready for usage.
    """
    db = get_mongodb_connection(container)
    for store in MongodbStores:
        if len(store.index_fields) > 1:
            index = []
            for field in store.index_fields:
                index.append((field, 1))
        else:
            index = store.index_fields[0]
        getattr(db, store.type).create_index(index, unique=True)
    return db
