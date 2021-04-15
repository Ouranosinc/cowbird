

class FSMonitor:
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
