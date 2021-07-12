import os
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


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
    """

    def __init__(self, path, recursive, callback):
        # type: (str, bool, FSMonitor) -> None
        """
        Initialize the path monitoring and ready to be started.

        @param path: Path to monitor
        @param recursive: Monitor subdirectory recursively?
        @param callback: Events are sent to this FSMonitor object
        """
        self.__callback = callback.get_instance()
        self.__src_path = os.path.normpath(path)
        self.__recursive = recursive
        self.__event_observer = Observer()

    @property
    def path(self):
        return self.__src_path

    @property
    def callback(self):
        return type(self.__callback)  # FIXME: Need the class name

    @property
    def callback_instance(self):
        return self.__callback

    @property
    def key(self):
        # type: () -> Dict
        """
        Return a dict that can be used as a unique key to identify this Monitor in a BD
        """
        return dict(callback=self.callback,
                    path=self.path)

    def params(self):
        # type: () -> Dict
        """
        Return a dict serializing this object from which a new Monitor can be recreated using the init function.
        """
        return dict(callback=self.callback,
                    path=self.path,
                    recursive=self.__recursive)

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