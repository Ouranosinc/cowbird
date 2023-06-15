from collections import defaultdict
from typing import TYPE_CHECKING

from cowbird.database import get_db
from cowbird.database.stores import MonitoringStore
from cowbird.monitoring.monitor import Monitor, MonitorException
from cowbird.utils import SingletonMeta, get_logger

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from typing import Optional, Type, Union

    from cowbird.monitoring.fsmonitor import FSMonitor
    from cowbird.typedefs import AnySettingsContainer

LOGGER = get_logger(__name__)


class MonitoringConfigurationException(Exception):
    """
    Exception thrown when the monitoring instance cannot be initialized because of a bad configuration.
    """


class Monitoring(metaclass=SingletonMeta):
    """
    Class handling file system monitoring and registering listeners.

    .. todo:: At some point we will need a consistency function that goes through all monitored folder and make sure
              that monitoring handlers are up to date.
    """

    def __init__(self, config=None):
        # type: (AnySettingsContainer) -> None
        """
        Initialize the monitoring instance from configured application settings.

        :param config: AnySettingsContainer object from which the db can be retrieved.
                       The default value of None is only there to disable pylint E1120. The singleton instance
                       must be initialized with a proper config and after that the init function should not be hit.
        """
        if not config:  # pragma: no cover
            raise MonitoringConfigurationException("Without proper application settings, the Monitoring class cannot "
                                                   "obtains a proper database store.")
        self.monitors = defaultdict(lambda: {})
        self.store = get_db(config).get_store(MonitoringStore)

    def start(self):
        """
        Load existing monitors and start the monitoring.
        """
        monitors = self.store.list_monitors()
        for mon in monitors:
            self.monitors[mon.path][mon.callback] = mon
            mon.start()

    def register(self, path, recursive, cb_monitor):
        # type: (str, bool, Union[FSMonitor, Type[FSMonitor], str]) -> Optional[Monitor]
        """
        Register a monitor for a specific path and start it. If a monitor already exists for the specific
        path/cb_monitor combination it is directly returned. If this monitor was not recursively monitoring its path and
        the `recursive` flag is now true, this one take precedence and the monitor is updated accordingly. If the
        `recursive` flag was true and now it is false it has no effect.

        :param path: Path to monitor
        :param recursive: Monitor subdirectory recursively?
        :param cb_monitor: FSMonitor for which an instance is created and events are sent
                           Can be an object, a class type implementing FSMonitor or a string containing module and class
                           name.
        :returns: The monitor registered or already existing for the specific path/cb_monitor combination. Note that
                  the monitor is not created/returned if a MonitorException occurs.
        """
        try:
            callback = Monitor.get_qualified_class_name(Monitor.get_fsmonitor_instance(cb_monitor))
            if path in self.monitors and callback in self.monitors[path]:
                mon = self.monitors[path][callback]
                # If the monitor already exists but is not recursive, make it recursive if required
                # (recursivity takes precedence)
                if not mon.recursive and recursive:
                    mon.recursive = True
            else:
                # Doesn't already exist
                mon = Monitor(path, recursive, cb_monitor)
                self.monitors[mon.path][mon.callback] = mon

            self.store.collection.update_one(
                {"callback": mon.callback, "path": mon.path},
                {"$set": {"callback": mon.callback, "path": mon.path, "recursive": mon.recursive}},
                upsert=True)

            if not mon.is_alive:
                mon.start()
            return mon
        except MonitorException as exc:
            LOGGER.warning("Failed to start monitoring the following path [%s] with this monitor [%s] : [%s]",
                           path, callback, exc)
        return None

    def unregister(self, path, cb_monitor):
        # type: (str, Union[FSMonitor, Type[FSMonitor], str]) -> bool
        """
        Stop a monitor and unregister it.

        :param path: Path used by the monitor
        :param cb_monitor: FSMonitor object to remove
                           Can be an object, a class type implementing FSMonitor or a string containing module and class
                           name.
        :returns: True if the monitor is found and successfully stopped, False otherwise
        """
        mon_qualname = Monitor.get_qualified_class_name(Monitor.get_fsmonitor_instance(cb_monitor))
        self.store.collection.delete_one({"callback": mon_qualname, "path": path})

        if path in self.monitors:
            try:
                mon = self.monitors[path].pop(mon_qualname)
                if len(self.monitors[path]) == 0:
                    self.monitors.pop(path)
                mon.stop()
                return True
            except KeyError:
                pass
        return False
