import os
from cowbird.services.service import Service
from cowbird.requestqueue import RequestQueue
from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring


class Catalog(Service, FSMonitor):
    """
    Keep the catalog index in synch when files are created/deleted/updated.
    """

    # FIXME: All services need to be singleton

    def __init__(self, name, url):
        super(Catalog, self).__init__(name, url)
        self.req_queue = RequestQueue()
        # TODO: Need to monitor data directory

    @staticmethod
    def _user_workspace_dir(self, username):
        # FIXME
        user_workspace_path = 'need value from settings'
        # TODO: path should already exists (priority on services hooks?)
        return os.path.join(user_workspace_path, username)

    def create_user(self, username):
        # TODO: Implement: what we do? start monitoring the user directory
        Monitoring().register(self._user_workspace_dir(username), True, self)

    def delete_user(self, username):
        Monitoring().unregister(self._user_workspace_dir(username), self)

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
