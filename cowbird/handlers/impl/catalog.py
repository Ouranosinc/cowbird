from typing import TYPE_CHECKING

from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring
from cowbird.handlers.handler import HANDLER_URL_PARAM, HANDLER_WORKSPACE_DIR_PARAM, Handler
from cowbird.utils import get_logger

if TYPE_CHECKING:
    from typing import Any

    # pylint: disable=W0611,unused-import
    from cowbird.typedefs import SettingsType

LOGGER = get_logger(__name__)


class Catalog(Handler, FSMonitor):
    """
    Keep the catalog index in sync when files are created/deleted/updated.
    """
    required_params = [HANDLER_URL_PARAM, HANDLER_WORKSPACE_DIR_PARAM]

    def __init__(self, settings, name, **kwargs):
        # type: (SettingsType, str, Any) -> None
        """
        Create the catalog instance.

        :param settings: Cowbird settings for convenience
        :param name: Handler name
        """
        super(Catalog, self).__init__(settings, name, **kwargs)
        # TODO: Need to monitor data directory

    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        raise NotImplementedError

    def user_created(self, user_name):
        LOGGER.info("Start monitoring workspace of created user [%s]", user_name)
        Monitoring().register(self._user_workspace_dir(user_name), True, Catalog)

    def user_deleted(self, user_name):
        LOGGER.info("Stop monitoring workspace of removed user [%s]", user_name)
        Monitoring().unregister(self._user_workspace_dir(user_name), self)

    def permission_created(self, permission):
        raise NotImplementedError

    def permission_deleted(self, permission):
        raise NotImplementedError

    @staticmethod
    def get_instance():
        """
        Return the Catalog singleton instance from the class name used to retrieve the FSMonitor from the DB.
        """
        from cowbird.handlers.handler_factory import HandlerFactory
        return HandlerFactory().get_handler("Catalog")

    def on_created(self, filename):
        """
        Call when a new file is found.

        :param filename: Relative filename of a new file
        """
        LOGGER.info("The following file [%s] has just been created", filename)

    def on_deleted(self, filename):
        """
        Call when a file is deleted.

        :param filename: Relative filename of the removed file
        """
        LOGGER.info("The following file [%s] has just been deleted", filename)

    def on_modified(self, filename):
        """
        Call when a file is updated.

        :param filename: Relative filename of the updated file
        """
        LOGGER.info("The following file [%s] has just been modified", filename)
