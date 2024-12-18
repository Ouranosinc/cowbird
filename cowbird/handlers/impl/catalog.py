from typing import Any, List, Optional

from cowbird.handlers.handler import HANDLER_URL_PARAM, HANDLER_WORKSPACE_DIR_PARAM, AnyHandlerParameter, Handler
from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring
from cowbird.permissions_synchronizer import Permission
from cowbird.typedefs import SettingsType
from cowbird.utils import get_logger

LOGGER = get_logger(__name__)


class Catalog(Handler, FSMonitor):
    """
    Keep the catalog index in sync when files are created/deleted/updated.
    """
    required_params: List[AnyHandlerParameter] = [HANDLER_URL_PARAM, HANDLER_WORKSPACE_DIR_PARAM]

    def __init__(self, settings: SettingsType, name: str, **kwargs: Any) -> None:
        """
        Create the catalog instance.

        :param settings: Cowbird settings for convenience
        :param name: Handler name
        """
        super(Catalog, self).__init__(settings, name, **kwargs)
        # TODO: Need to monitor data directory

    def user_created(self, user_name: str) -> None:
        LOGGER.info("Start monitoring workspace of created user [%s]", user_name)
        Monitoring().register(self._user_workspace_dir(user_name), True, Catalog)

    def user_deleted(self, user_name: str) -> None:
        LOGGER.info("Stop monitoring workspace of removed user [%s]", user_name)
        Monitoring().unregister(self._user_workspace_dir(user_name), self)

    def permission_created(self, permission: Permission) -> None:
        LOGGER.info("Event [permission_created] for handler [%s] is not implemented", self.name)

    def permission_deleted(self, permission: Permission) -> None:
        LOGGER.info("Event [permission_deleted] for handler [%s] is not implemented", self.name)

    @staticmethod
    def get_instance() -> Optional["Catalog"]:
        """
        Return the Catalog singleton instance from the class name used to retrieve the FSMonitor from the DB.
        """
        from cowbird.handlers.handler_factory import HandlerFactory
        return HandlerFactory().get_handler("Catalog")

    def on_created(self, path: str) -> None:
        """
        Called when a new path is found.

        :param path: Absolute path of a new file/directory
        """
        LOGGER.info("The following path [%s] has just been created", path)

    def on_deleted(self, path: str) -> None:
        """
        Called when a path is deleted.

        :param path: Absolute path of a new file/directory
        """
        LOGGER.info("The following path [%s] has just been deleted", path)

    def on_modified(self, path: str) -> None:
        """
        Called when a path is updated.

        :param path: Absolute path of a new file/directory
        """
        LOGGER.info("The following path [%s] has just been modified", path)

    def resync(self) -> None:
        # FIXME: this should be implemented in the eventual task addressing the resync mechanism.
        LOGGER.warning("Event [resync] for handler [%s] is not implemented but should be in the future", self.name)
