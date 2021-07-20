import abc


class FSMonitor(abc.ABC):
    """
    Interface being called when something chang on the filesystem.
    """

    @staticmethod
    @abc.abstractmethod
    def get_instance():
        """
        Must return a monitor instance.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def on_created(self, filename):
        # type: (str) -> None
        """
        Call when a new file is found.

        :param filename: Relative filename of a new file
        """
        raise NotImplementedError

    @abc.abstractmethod
    def on_deleted(self, filename):
        # type: (str) -> None
        """
        Call when a file is deleted.

        :param filename: Relative filename of the removed file
        """
        raise NotImplementedError

    @abc.abstractmethod
    def on_modified(self, filename):
        # type: (str) -> None
        """
        Call when a file is updated.

        :param filename: Relative filename of the updated file
        """
        raise NotImplementedError
