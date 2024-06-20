import importlib
import os
from typing import Optional, Type, TypedDict, Union

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEventHandler
)
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.utils import get_logger

LOGGER = get_logger(__name__)

MonitorKey = TypedDict(
    "MonitorKey",
    {
        "callback": str,
        "path": str,
    },
    total=True,
)
MonitorParameters = TypedDict(
    "MonitorParameters",
    {
        "callback": str,
        "path": str,
        "recursive": bool,
    },
    total=True,
)


class MonitorException(Exception):
    """
    Error indicating that a :class:`Monitor` cannot be started because of an invalid path or callback.
    """


class Monitor(FileSystemEventHandler):
    """
    Implementation of the watchdog :class:`FileSystemEventHandler` class Allows to start/stop directory monitoring and
    send events to :class:`FSMonitor` callback.
    """

    def __init__(self, path: str, recursive: bool, callback: Union[FSMonitor, Type[FSMonitor], str]) -> None:
        """
        Initialize the path monitoring and ready to be started.

        :param path: Path to monitor
        :param recursive: Monitor subdirectory recursively?
        :param callback: Events are sent to this FSMonitor.
                         Can be an object, a class type implementing :class:`FSMonitor` or a string containing module
                         and class name. The class type or string is used to instantiate an object using the class
                         method :meth:`FSMonitor.get_instance()`
        """
        if not os.path.exists(path):
            raise MonitorException(f"Cannot monitor the following file or directory [{path}]: "
                                   "No such file or directory")
        self.__src_path = path
        self.__recursive = recursive
        self.__callback = self.get_fsmonitor_instance(callback)
        self.__event_observer: Optional[BaseObserver] = None

    @staticmethod
    def get_fsmonitor_instance(callback: Union[FSMonitor, Type[FSMonitor], str]) -> FSMonitor:
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
                raise MonitorException(f"Cannot instantiate the following FSMonitor callback : {callback}")
        raise TypeError(f"Unsupported callback type : [{callback}] ({type(callback)})")

    @staticmethod
    def get_qualified_class_name(monitor: FSMonitor) -> str:
        """
        Returns the full qualified class name of the :class:`FSMonitor` object (string of the form module.class_name)
        """
        cls = type(monitor)
        return ".".join([cls.__module__, cls.__qualname__])

    @property
    def recursive(self) -> bool:
        return self.__recursive

    @recursive.setter
    def recursive(self, value: bool) -> None:
        if self.__recursive != value:
            self.stop()
            self.__recursive = value
            self.start()

    @property
    def path(self) -> str:
        return self.__src_path

    @property
    def callback(self) -> str:
        return self.get_qualified_class_name(self.__callback)

    @property
    def callback_instance(self) -> FSMonitor:
        return self.__callback

    @property
    def key(self) -> MonitorKey:
        """
        Return a dict that can be used as a unique key to identify this :class:`Monitor` in a BD.
        """
        return {"callback": self.callback, "path": self.path}

    @property
    def is_alive(self) -> bool:
        """
        Returns true if the monitor observer exists and is currently running.
        """
        return bool(self.__event_observer) and self.__event_observer.is_alive()

    def params(self) -> MonitorParameters:
        """
        Return a dict serializing this object from which a new :class:`Monitor` can be recreated using the init
        function.
        """
        return {"callback": self.callback, "path": self.path, "recursive": self.__recursive}

    def start(self) -> None:
        """
        Start the monitoring so that events can be fired.
        """
        if self.is_alive:
            msg = f"This monitor [path={self.path}, callback={self.callback}] is already started"
            LOGGER.error(msg)
            raise MonitorException(msg)
        self.__event_observer = Observer()
        self.__event_observer.schedule(self,  # type: ignore[no-untyped-call]
                                       self.__src_path,
                                       recursive=self.__recursive)
        try:
            self.__event_observer.start()  # type: ignore[no-untyped-call]
        except OSError:
            LOGGER.warning("Cannot monitor the following file or directory [%s]: No such file or directory",
                           self.__src_path)

    def stop(self) -> None:
        """
        Stop the monitoring so that events stop to be fired.
        """
        self.__event_observer.stop()  # type: ignore[no-untyped-call]
        self.__event_observer.join()
        self.__event_observer = None

    def on_moved(self, event: Union[DirMovedEvent, FileMovedEvent]) -> None:  # type: ignore[override]
        """
        Called when a file or a directory is moved or renamed.

        :param event: Event representing file/directory movement.
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

    def on_created(self, event: Union[DirCreatedEvent, FileCreatedEvent]) -> None:  # type: ignore[override]
        """
        Called when a file or directory is created.

        :param event: Event representing file/directory creation.
        """
        self.__callback.on_created(event.src_path)

    def on_deleted(self, event: Union[DirDeletedEvent, FileDeletedEvent]) -> None:  # type: ignore[override]
        """
        Called when a file or directory is deleted.

        :param event: Event representing file/directory deletion.
        """
        self.__callback.on_deleted(event.src_path)

    def on_modified(self, event: Union[DirModifiedEvent, FileModifiedEvent]) -> None:  # type: ignore[override]
        """
        Called when a file or directory is modified.

        :param event: Event representing file/directory modification.
        """
        self.__callback.on_modified(event.src_path)
