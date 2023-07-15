# MongoDB
# http://docs.pylonsproject.org/projects/pyramid-cookbook/en/latest/database/mongodb.html
import warnings
from typing import Any, Dict, Optional, Type, Union, cast
from urllib.parse import urlparse

import pymongo
from pymongo.database import Database

from cowbird.database.base import DatabaseInterface, StoreSelector
from cowbird.database.stores import MonitoringStore, StoreInterface
from cowbird.typedefs import JSON, AnySettingsContainer
from cowbird.utils import get_settings

# pylint: disable=C0103,invalid-name
MongoDB: Optional[Database] = None
MongodbStores = frozenset([
    MonitoringStore,
])

AnyMongodbStore = Union[MonitoringStore]
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

    def __init__(self, container: AnySettingsContainer) -> None:
        """
        Initialize the mongo database from various type of container.
        """
        super(MongoDatabase, self).__init__(container)
        self._database = get_mongodb_engine(container)
        self._settings = get_settings(container)
        self._stores: Dict[str, AnyMongodbStore] = {}

    def reset_store(self, store_type: AnyMongodbStoreType) -> Optional[AnyMongodbStore]:
        store_type = self._get_store_type(store_type)
        return self._stores.pop(store_type, None)

    def get_store(self,
                  store_type: Union[str, Type[StoreInterface], AnyMongodbStoreType],
                  *store_args: Any,
                  **store_kwargs: Any,
                  ) -> AnyMongodbStore:
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

    def get_session(self) -> Any:
        return self._database

    def get_information(self) -> JSON:
        """
        :returns: {'version': version, 'type': db_type}
        """
        result = list(self._database.version.find().limit(1))[0]
        db_version = result["version_num"]
        return {"version": db_version, "type": self.type}

    def is_ready(self) -> bool:
        return self._database is not None and self._settings is not None


def get_mongodb_connection(container: AnySettingsContainer) -> Database:
    """
    Obtains the basic database connection from settings.
    """

    settings = get_settings(container)
    default_mongo_uri = "mongodb://0.0.0.0:27017/cowbird"
    if settings.get("mongo_uri", None) is None:
        warnings.warn(f"Setting 'mongo_uri' not defined in registry, using default [{default_mongo_uri}].")
        settings["mongo_uri"] = default_mongo_uri
    db_url = urlparse(cast(str, settings["mongo_uri"]))
    client = pymongo.MongoClient(
        host=db_url.hostname,
        port=db_url.port,
        username=db_url.username or None,
        password=db_url.password or None,
    )
    db = client[db_url.path[1:]]
    return db


def get_mongodb_engine(container: AnySettingsContainer) -> Database:
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
