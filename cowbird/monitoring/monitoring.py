import os
from collections import defaultdict
from typing import TYPE_CHECKING

import six
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from cowbird.utils import SingletonMeta

if TYPE_CHECKING:
    from typing import Union

    from watchdog.events import (
        DirCreatedEvent,
        DirDeletedEvent,
        DirModifiedEvent,
        DirMovedEvent,
        FileCreatedEvent,
        FileDeletedEvent,
        FileModifiedEvent,
        FileMovedEvent
    )

    from cowbird.monitoring.fsmonitor import FSMonitor


class Monitor(FileSystemEventHandler):
    """
    Implementation of the watchdog FileSystemEventHandler class Allows to start/stop directory monitoring and send
    events to FSMonitor callback.

    .. todo:: This class should be mapped as a BD model
              (we need to persist monitors across executions)
    """

    def __init__(self, path, recursive, callback):
        # type: (str, bool, FSMonitor) -> None
        """
        Initialize the path monitoring and ready to be started.

        .. TODO:: To serialize the callback we would need an actual singleton class name

        @param path: Path to monitor
        @param recursive: Monitor subdirectory recursively?
        @param callback: Events are sent to this FSMonitor object
        """
        self.__callback = callback
        self.__src_path = os.path.normpath(path)
        self.__recursive = recursive
        self.__event_observer = Observer()

    def save(self):
        """
        .. TODO: Serialize the monitor to a database
        """

    def remove(self):
        """
        .. TODO: Remove the monitor from the database
        """

    def start(self):
        """
        Start the monitoring so that events can be fired.
        """
        self.__event_observer.schedule(self,
                                       self.__src_path,
                                       recursive=self.__recursive)
        self.__event_observer.start()

    def stop(self):
        """
        Stop the monitoring so that events stop to be fired.
        """
        self.__event_observer.stop()
        self.__event_observer.join()

    def on_moved(self, event):
        # type: (Union[DirMovedEvent, FileMovedEvent]) -> None
        """
        Called when a file or a directory is moved or renamed.

        @param event: Event representing file/directory movement.
        """
        self.__callback.on_deleted(event.src_path)
        # If moved outside of __src_path don't send a create event
        if event.dest_path.startswith(self.__src_path):
            # If move under subdirectory and recursive is False don't send a
            # create event neither
            if self.__recursive or \
                    os.path.dirname(event.dest_path) == \
                    os.path.dirname(self.__src_path):
                self.__callback.on_created(event.dest_path)

    def on_created(self, event):
        # type: (Union[DirCreatedEvent, FileCreatedEvent]) -> None
        """
        Called when a file or directory is created.

        @param event: Event representing file/directory creation.
        """
        self.__callback.on_created(event.src_path)

    def on_deleted(self, event):
        # type: (Union[DirDeletedEvent, FileDeletedEvent]) -> None
        """
        Called when a file or directory is deleted.

        @param event: Event representing file/directory deletion.
        """
        self.__callback.on_deleted(event.src_path)

    def on_modified(self, event):
        # type: (Union[DirModifiedEvent, FileModifiedEvent]) -> None
        """
        Called when a file or directory is modified.

        @param event: Event representing file/directory modification.
        """
        self.__callback.on_modified(event.src_path)


@six.add_metaclass(SingletonMeta)
class Monitoring:
    """
    Class handling file system monitoring and registering listeners.

    .. todo:: At some point we will need a consistency function that goes through all monitored folder and make sure
              that monitoring services are up to date.
    """

    def __init__(self):
        self.monitors = defaultdict(lambda: {})

    def start(self):
        """
        .. todo:: Load and start monitors from the BD
        """

    def register(self, path, recursive, cb_monitor):
        # type: (str, bool, FSMonitor) -> None
        """
        Register a monitor for a specific path and start it.

        @param path: Path to monitor
        @param recursive: Monitor subdirectory recursively?
        @param cb_monitor: Events are sent to this FSMonitor object
        """
        try:
            self.monitors[path][cb_monitor]
        except KeyError:
            # Doesn't already exist
            mon = Monitor(path, recursive, cb_monitor)
            self.monitors[path][cb_monitor] = mon
            mon.save()
            mon.start()

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
                mon.remove()
                return True
            except KeyError:
                pass
        return False
