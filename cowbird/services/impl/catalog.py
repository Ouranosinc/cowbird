from cowbird.services.service import Service
from cowbird.requestqueue import RequestQueue
from cowbird.monitoring import IFSMonitor


class Catalog(Service, IFSMonitor):
    """
    Keep the catalog index in synch when files are created/deleted/updated.
    """

    # FIXME: All services need to be singleton as well as monitoring

    def __init__(self, name):
        super(Catalog, self).__init__(name)
        self.req_queue = RequestQueue()
        # TODO: Need to monitor data directory

    def create_user(self, username):
        # TODO: Implement: what we do? start monitoring the user directory
        pass

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
