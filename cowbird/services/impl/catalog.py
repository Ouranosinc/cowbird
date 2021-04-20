import os

from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring
from cowbird.request_queue import RequestQueue
from cowbird.services.service import Service


class Catalog(Service, FSMonitor):
    """
    Keep the catalog index in synch when files are created/deleted/updated.
    """

    def __init__(self, name, url):
        super(Catalog, self).__init__(name, url)
        self.req_queue = RequestQueue()
        # TODO: Need to monitor data directory

    @staticmethod
    def _user_workspace_dir(username):
        # FIXME
        user_workspace_path = "need value from settings"
        # TODO: path should already exists (priority on services hooks?)
        return os.path.join(user_workspace_path, username)

    def create_user(self, username):
        # TODO: Implement: what we do? start monitoring the user directory
        Monitoring().register(self._user_workspace_dir(username), True, self)

    def delete_user(self, username):
        Monitoring().unregister(self._user_workspace_dir(username), self)

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
