import importlib
import os
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.utils import get_logger

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from typing import Dict, Type, Union

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

LOGGER = get_logger(__name__)


class MonitorException(Exception):
    """
    Error indicating that a :class:`Monitor` cannot be started because of an invalid path or callback.
    """


class Monitor(FileSystemEventHandler):
    """
    Implementation of the watchdog :class:`FileSystemEventHandler` class Allows to start/stop directory monitoring and
    send events to :class:`FSMonitor` callback.
    """

    def __init__(self, path, recursive, callback):
        # type: (str, bool, Union[FSMonitor, Type[FSMonitor], str]) -> None
        """
        Initialize the path monitoring and ready to be started.

        @param path: Path to monitor
        @param recursive: Monitor subdirectory recursively?
        @param callback: Events are sent to this FSMonitor.
                         Can be an object, a class type implementing :class:`FSMonitor` or a string containing module
                         and class name. The class type or string is used to instantiate an object using the class
                         method `FSMonitor.get_instance()`
        """
        if not os.path.exists(path):
            raise MonitorException("Cannot monitor the following file or directory [{}]: No such file or directory"
                                   .format(path))
        self.__src_path = path
        self.__recursive = recursive
        self.__callback = self.get_fsmonitor_instance(callback)
        self.__event_observer = None

    @staticmethod
    def get_fsmonitor_instance(callback):
        # type: (Union[FSMonitor, Type[FSMonitor], str]) -> FSMonitor
        """
        Return a :class:`FSMonitor` instance from multiple possible forms including the :class:`FSMonitor` type, the
        :class:`FSMonitor` full qualified class name or a direct instance which is returned as is.
        """
        if isinstance(callback, FSMonitor):
            return callback
        if isinstance(callback, type) and issubclass(callback, FSMonitor):
            return callback.get_instance()
        if isinstance(callback, str):
            try:
                module_name = ".".join(callback.split(".")[:-1])
                class_name = callback.split(".")[-1]
                module = importlib.import_module(module_name)
                cls = getattr(module, class_name)
                return cls.get_instance()
            except (AttributeError, ValueError):
                raise MonitorException("Cannot instantiate the following FSMonitor callback : {}".format(callback))
        raise TypeError("Unsupported callback type : [{}] ({})".format(callback, type(callback)))

    @staticmethod
    def get_qualified_class_name(monitor):
        # type: (FSMonitor) -> str
        """
        Returns the full qualified class name of the :class:`FSMonitor` object (string of the form module.class_name)
        """
        cls = type(monitor)
        return ".".join([cls.__module__, cls.__qualname__])

    @property
    def recursive(self):
        return self.__recursive

    @recursive.setter
    def recursive(self, value):
        if self.__recursive != value:
            self.stop()
            self.__recursive = value
            self.start()

    @property
    def path(self):
        return self.__src_path

    @property
    def callback(self):
        return self.get_qualified_class_name(self.__callback)

    @property
    def callback_instance(self):
        return self.__callback

    @property
    def key(self):
        # type: () -> Dict
        """
        Return a dict that can be used as a unique key to identify this :class:`Monitor` in a BD.
        """
        return dict(callback=self.callback,
                    path=self.path)

    def params(self):
        # type: () -> Dict
        """
        Return a dict serializing this object from which a new :class:`Monitor` can be recreated using the init
        function.
        """
        return dict(callback=self.callback,
                    path=self.path,
                    recursive=self.__recursive)

    def start(self):
        """
        Start the monitoring so that events can be fired.
        """
        if self.__event_observer:
            msg = "This monitor [path={}, callback={}] is already started".format(self.path,
                                                                                  self.callback)
            LOGGER.error(msg)
            raise MonitorException(msg)
        self.__event_observer = Observer()
        self.__event_observer.schedule(self,
                                       self.__src_path,
                                       recursive=self.__recursive)
        try:
            self.__event_observer.start()
        except OSError:
            LOGGER.warning("Cannot monitor the following file or directory [%s]: No such file or directory",
                           self.__src_path)

    def stop(self):
        """
        Stop the monitoring so that events stop to be fired.
        """
        self.__event_observer.stop()
        self.__event_observer.join()
        self.__event_observer = None

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
