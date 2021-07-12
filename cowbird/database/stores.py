"""
Stores to read/write data to from/to `MongoDB` using pymongo.
"""

import abc
import logging
from typing import TYPE_CHECKING

import pymongo

from cowbird.monitoring.monitor import Monitor

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Tuple, Union, Type
    from pymongo.collection import Collection

LOGGER = logging.getLogger(__name__)


class StoreInterface(object, metaclass=abc.ABCMeta):
    type = None

    def __init__(self):
        if not self.type:
            raise NotImplementedError("Store 'type' must be overridden in inheriting class.")


class MongodbStore:
    """
    Base class extended by all concrete store implementations.
    """

    def __init__(self, collection, sane_name_config=None):
        # type: (Collection, Optional[Dict[str, Any]]) -> None
        if not isinstance(collection, pymongo.collection.Collection):
            raise TypeError("Collection not of expected type.")
        self.collection = collection  # type: Collection
        self.sane_name_config = sane_name_config or {}

    @classmethod
    def get_args_kwargs(cls, *args, **kwargs):
        # type: (*Any, **Any) -> Tuple[Tuple, Dict]
        """
        Filters :class:`MongodbStore`-specific arguments to safely pass them down its ``__init__``.
        """
        collection = None
        if len(args):
            collection = args[0]
        elif "collection" in kwargs:    # pylint: disable=R1715
            collection = kwargs["collection"]
        sane_name_config = kwargs.get("sane_name_config", None)
        return tuple([collection]), {"sane_name_config": sane_name_config}


class MonitoringStore(StoreInterface, MongodbStore):
    """
    Registry for monitoring instances. Uses `MongoDB` to store what is monitored and by whom.
    """
    type = "monitors"

    def __init__(self, *args, **kwargs):
        db_args, db_kwargs = MongodbStore.get_args_kwargs(*args, **kwargs)
        StoreInterface.__init__(self)
        MongodbStore.__init__(self, *db_args, **db_kwargs)

    def save_monitor(self, monitor):
        # type: (Monitor) -> bool
        """
        Stores Monitor in `MongoDB` storage.
        """
        # check if the Monitor is already registered
        if self.collection.count_documents(monitor.key) > 0:
            self.collection.delete_one(monitor.key)
        self.collection.insert_one(monitor.params())
        return True

    def delete_monitor(self, monitor):
        # type: (Monitor) -> bool
        """
        Removes Monitor from `MongoDB` storage.
        """
        self.collection.delete_one(monitor.key)
        return True

    def list_monitors(self):
        # type: () -> List[Monitor]
        """
        Lists all Monitor in `MongoDB` storage.
        """
        monitors = []
        for mon_params in self.collection.find().sort("callback", pymongo.ASCENDING):
            monitors.append(Monitor(**mon_params))
        return monitors

    def clear_services(self):
        # type: () -> bool
        """
        Removes all Monitor from `MongoDB` storage.
        """
        self.collection.drop()
        return True
