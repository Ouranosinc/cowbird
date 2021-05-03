import os
from collections import defaultdict

import six
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from cowbird.utils import SingletonMeta


class Monitor(FileSystemEventHandler):
    """
    .. todo:: This class should be mapped as a BD model

    # (we need to persist monitors across executions)
    """

    def __init__(self, path, recursive, callback):
        # TODO: To serialize the callback we would probably need an actual
        #  singleton class name
        self.__callback = callback
        self.__src_path = os.path.normpath(path)
        self.__recursive = recursive
        self.__event_observer = Observer()

    def save(self):
        # TODO Save to DB
        pass

    def remove(self):
        # TODO Remove from DB
        pass

    def start(self):
        self.__event_observer.schedule(self,
                                       self.__src_path,
                                       recursive=self.__recursive)
        self.__event_observer.start()

    def stop(self):
        self.__event_observer.stop()
        self.__event_observer.join()

    def on_moved(self, event):
        """
        Called when a file or a directory is moved or renamed.

        :param event:
            Event representing file/directory movement.
        :type event:
            :class:`DirMovedEvent` or :class:`FileMovedEvent`
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
        """
        Called when a file or directory is created.

        :param event:
            Event representing file/directory creation.
        :type event:
            :class:`DirCreatedEvent` or :class:`FileCreatedEvent`
        """
        self.__callback.on_created(event.src_path)

    def on_deleted(self, event):
        """
        Called when a file or directory is deleted.

        :param event:
            Event representing file/directory deletion.
        :type event:
            :class:`DirDeletedEvent` or :class:`FileDeletedEvent`
        """
        self.__callback.on_deleted(event.src_path)

    def on_modified(self, event):
        """
        Called when a file or directory is modified.

        :param event:
            Event representing file/directory modification.
        :type event:
            :class:`DirModifiedEvent` or :class:`FileModifiedEvent`
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
        # TODO: Load and start monitors from the BD
        pass

    def register(self, path, recursive, cb_monitor):
        try:
            self.monitors[path][cb_monitor]
        except KeyError:
            # Doesn't already exist
            mon = Monitor(path, recursive, cb_monitor)
            self.monitors[path][cb_monitor] = mon
            mon.save()
            mon.start()

    def unregister(self, path, cb_monitor):
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
