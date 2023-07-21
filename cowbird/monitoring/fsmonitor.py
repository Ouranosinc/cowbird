import abc
from typing import Optional


class FSMonitor(abc.ABC):
    """
    Interface being called when something changes on the filesystem.
    """

    @staticmethod
    @abc.abstractmethod
    def get_instance() -> Optional["FSMonitor"]:
        """
        Must return an instance of the class implementing FSMonitor.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def on_created(self, path: str) -> None:
        """
        Called when a new path is found.

        :param path: Absolute path of a new file/directory
        """
        raise NotImplementedError

    @abc.abstractmethod
    def on_deleted(self, path: str) -> None:
        """
        Called when a path is deleted.

        :param path: Absolute path of a new file/directory
        """
        raise NotImplementedError

    @abc.abstractmethod
    def on_modified(self, path: str) -> None:
        """
        Called when a path is updated.

        :param path: Absolute path of a new file/directory
        """
        raise NotImplementedError
