from typing import Any

from cowbird.handlers.handler import Handler
from cowbird.permissions_synchronizer import Permission
from cowbird.typedefs import SettingsType
from cowbird.utils import get_logger

LOGGER = get_logger(__name__)


class Nginx(Handler):
    """
    Nothing to do right now.
    """
    required_params = []

    def __init__(self, settings: SettingsType, name: str, **kwargs: Any) -> None:
        """
        Create the nginx instance.

        :param settings: Cowbird settings for convenience
        :param name: Handler name
        """
        super(Nginx, self).__init__(settings, name, **kwargs)

    def user_created(self, user_name: str) -> None:
        LOGGER.info("Event [user_created] for handler [%s] is not implemented", self.name)

    def user_deleted(self, user_name: str) -> None:
        LOGGER.info("Event [user_deleted] for handler [%s] is not implemented", self.name)

    def permission_created(self, permission: Permission) -> None:
        LOGGER.info("Event [permission_created] for handler [%s] is not implemented", self.name)

    def permission_deleted(self, permission: Permission) -> None:
        LOGGER.info("Event [permission_deleted] for handler [%s] is not implemented", self.name)

    def resync(self) -> None:
        # FIXME: this should be implemented in the eventual task addressing the resync mechanism.:
        LOGGER.warning("Event [resync] for handler [%s] is not implemented but should be in the future", self.name)
