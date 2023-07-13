"""
Stores to read/write data to from/to `MongoDB` using pymongo.
"""

import abc
import logging
from typing import Any, Dict, List, Optional, Tuple

import pymongo
from pymongo.collection import Collection

from cowbird.monitoring.monitor import Monitor, MonitorException

LOGGER = logging.getLogger(__name__)


class StoreInterface(object, metaclass=abc.ABCMeta):
    # Store type being used as collection name in mongo and to retrieve a store
    type = None

    # Fields name used as index inside the mongo collection, with a length > 1, a compound index is created
    index_fields = []

    def __init__(self):
        """
        Check that the store implementation defines its type and index_fields.
        """
        if not self.type:
            raise NotImplementedError("Store 'type' must be overridden in inheriting class.")
        if not self.index_fields:
            raise NotImplementedError("Store 'index_fields' must be overridden in inheriting class.")


class MongodbStore:
    """
    Base class extended by all concrete store implementations.
    """

    def __init__(self: Collection, collection: Optional[Dict[str, Any]]) -> None:
        """
        Validate and hold the collection for all the implementation.
        """
        if not isinstance(collection, pymongo.collection.Collection):
            raise TypeError("Collection not of expected type.")
        self.collection: Collection = collection

    @classmethod
    def get_args_kwargs(cls, *args: Any, **kwargs: Any) -> Tuple[Tuple, Dict]:
        """
        Filters :class:`MongodbStore`-specific arguments to safely pass them down its ``__init__``.
        """
        if len(args):
            collection = args[0]
        else:
            collection = kwargs.get("collection", None)
        return tuple([collection]), {}


class MonitoringStore(StoreInterface, MongodbStore):
    """
    Registry for monitoring instances.

    Uses `MongoDB` to store what is monitored and by whom.
    """
    type = "monitors"
    index_fields = ["callback", "path"]

    def __init__(self, *args, **kwargs):
        """
        Init the store used to save monitors.
        """
        db_args, db_kwargs = MongodbStore.get_args_kwargs(*args, **kwargs)
        StoreInterface.__init__(self)
        MongodbStore.__init__(self, *db_args, **db_kwargs)

    def save_monitor(self, monitor: Monitor) -> None:
        """
        Stores Monitor in `MongoDB` storage.
        """
        # check if the Monitor is already registered
        if self.collection.count_documents(monitor.key) > 0:
            self.collection.delete_one(monitor.key)
        self.collection.insert_one(monitor.params())

    def delete_monitor(self, monitor: Monitor) -> None:
        """
        Removes Monitor from `MongoDB` storage.
        """
        self.collection.delete_one(monitor.key)

    def list_monitors(self) -> List[Monitor]:
        """
        Lists all Monitor in `MongoDB` storage.
        """
        monitors = []
        for mon_params in self.collection.find().sort("callback", pymongo.ASCENDING):
            try:
                monitors.append(Monitor(**{key: val for key, val in mon_params.items() if key != "_id"}))
            except MonitorException as exc:
                LOGGER.warning("Failed to start monitoring the following path [%s] with this monitor [%s] "
                               "(Will be removed from database) : [%s]",
                               mon_params["path"],
                               mon_params["callback"],
                               exc)
                self.collection.delete_one(mon_params)
        return monitors

    def clear_services(self, drop: bool = True) -> None:
        """
        Removes all Monitor from `MongoDB` storage.
        """
        if drop:
            self.collection.drop()
        else:
            self.collection.delete_many({})
