from collections import defaultdict
from typing import TYPE_CHECKING

from cowbird.monitoring.monitor import Monitor
from cowbird.database import get_db
from cowbird.database.stores import MonitoringStore
from cowbird.utils import SingletonMeta

if TYPE_CHECKING:
    from cowbird.monitoring.fsmonitor import FSMonitor


class Monitoring(metaclass=SingletonMeta):
    """
    Class handling file system monitoring and registering listeners.

    .. todo:: At some point we will need a consistency function that goes through all monitored folder and make sure
              that monitoring services are up to date.
    """

    def __init__(self, config):
        self.monitors = defaultdict(lambda: {})
        self.store = get_db(config).get_store(MonitoringStore)

    def start(self):
        """
        Load existing monitors and start the monitoring
        """
        monitors = self.store.list_monitors()
        for mon in monitors:
            self.monitors[mon.path][mon.callback] = mon
            mon.start()

    def register(self, path, recursive, cb_monitor):
        # type: (str, bool, Type[FSMonitor]) -> Monitor
        """
        Register a monitor for a specific path and start it.

        @param path: Path to monitor
        @param recursive: Monitor subdirectory recursively?
        @param cb_monitor: FSMonitor type for which an instance is created and events are sent
        """
        try:
            return self.monitors[path][cb_monitor]
        except KeyError:
            # Doesn't already exist
            mon = Monitor(path, recursive, cb_monitor)
            self.monitors[path][cb_monitor] = mon
            self.store.save_monitor(mon)
            mon.start()
            return mon

    def unregister(self, path, cb_monitor):
        # type: (str, FSMonitor) -> bool
        """
        Stop a monitor and unregister it.

        @param path: Path used by the monitor
        @param cb_monitor: FSMonitor object to remove
        @return: True if the monitor is found and successfully stopped, False otherwise
        """
        if path in self.monitors:
            try:
                mon = self.monitors[path].pop(cb_monitor)
                if len(self.monitors[path]) == 0:
                    self.monitors.pop(path)
                mon.stop()
                self.store.delete_monitor(mon)
                return True
            except KeyError:
                pass
        return False
