import os

from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring
from cowbird.services.service import Service
from cowbird.utils import get_logger

logger = get_logger(__name__)


class Catalog(Service, FSMonitor):
    """
    Keep the catalog index in sync when files are created/deleted/updated.
    """

    def __init__(self, name, url):
        super(Catalog, self).__init__(name, url)
        # TODO: Need to monitor data directory

    @staticmethod
    def _user_workspace_dir(user_name):
        # FIXME
        user_workspace_path = "need value from settings"
        # TODO: path should already exists (priority on services hooks?)
        return os.path.join(user_workspace_path, user_name)

    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        raise NotImplementedError

    def user_created(self, user_name):
        logger.info("Start monitoring workspace of user [%s]", user_name)
        # TODO: Implement: what we do? start monitoring the user directory
        Monitoring().register(self._user_workspace_dir(user_name), True, self)

    def user_deleted(self, user_name):
        Monitoring().unregister(self._user_workspace_dir(user_name), self)

    def permission_created(self, permission):
        raise NotImplementedError

    def permission_deleted(self, permission):
        raise NotImplementedError

    def on_created(self, filename):
        """
        Call when a new file is found.

        :param filename: Relative filename of a new file
        """
        raise NotImplementedError

    def on_deleted(self, filename):
        """
        Call when a file is deleted.

        :param filename: Relative filename of the removed file
        """
        raise NotImplementedError

    def on_modified(self, filename):
        """
        Call when a file is updated.

        :param filename: Relative filename of the updated file
        """
        raise NotImplementedError
