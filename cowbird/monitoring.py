from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class IFSMonitor:
    """
    Interface being called when something chang on the filesystem
    """
    def on_created(self, fn):
        """
        Call when a new file is found
        :param fn: Relative filename of a new file
        """
        pass

    def on_deleted(self, fn):
        """
        Call when a file is deleted
        :param fn: Relative filename of the removed file
        """
        pass

    def on_modified(self, fn):
        """
        Call when a file is updated
        :param fn: Relative filename of the updated file
        """
        pass


class Monitor(FileSystemEventHandler):
    def __init__(self, path, recursive, callback):
        self.__callback = callback
        self.__src_path = path
        self.__recursive = recursive
        self.__event_observer = Observer()

    def start(self):
        self.__event_observer.schedule(self,
                                       self.__src_path,
                                       recursive=self.__recursive)
        self.__event_observer.start()

    def stop(self):
        self.__event_observer.stop()
        self.__event_observer.join()

    def on_moved(self, event):
        """Called when a file or a directory is moved or renamed.

        :param event:
            Event representing file/directory movement.
        :type event:
            :class:`DirMovedEvent` or :class:`FileMovedEvent`
        """
        # FIXME: Check that dest_path is under self.__src_path else don't send
        #        on_created event
        self.__callback.on_deleted(event.src_path)
        self.__callback.on_created(event.dest_path)

    def on_created(self, event):
        """Called when a file or directory is created.

        :param event:
            Event representing file/directory creation.
        :type event:
            :class:`DirCreatedEvent` or :class:`FileCreatedEvent`
        """
        self.__callback.on_created(event.src_path)

    def on_deleted(self, event):
        """Called when a file or directory is deleted.

        :param event:
            Event representing file/directory deletion.
        :type event:
            :class:`DirDeletedEvent` or :class:`FileDeletedEvent`
        """
        self.__callback.on_deleted(event.src_path)

    def on_modified(self, event):
        """Called when a file or directory is modified.

        :param event:
            Event representing file/directory modification.
        :type event:
            :class:`DirModifiedEvent` or :class:`FileModifiedEvent`
        """
        self.__callback.on_modified(event.src_path)


class Monitoring:
    """
    Class handling file system monitoring and registering listeners
    """
    def __init__(self):
        self.monitors = []

    def register(self, path, recursive, cb_monitor):
        mon = Monitor(path, recursive, cb_monitor)
        mon.start()
        self.monitors.append(mon)

    def unregister(self, cb_monitor):
        try:
            mon = self.monitors.pop(self.monitors.find(cb_monitor))
            mon.stop()
            return True
        except ValueError:
            return False
