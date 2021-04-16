

class FSMonitor:
    """
    Interface being called when something chang on the filesystem.
    """

    def on_created(self, filename):
        """
        Call when a new file is found.

        :param filename: Relative filename of a new file
        """

    def on_deleted(self, filename):
        """
        Call when a file is deleted.

        :param filename: Relative filename of the removed file
        """

    def on_modified(self, filename):
        """
        Call when a file is updated.

        :param filename: Relative filename of the updated file
        """
