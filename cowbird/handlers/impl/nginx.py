from typing import Any

from cowbird.handlers.handler import Handler
from cowbird.permissions_synchronizer import Permission
from cowbird.typedefs import SettingsType


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
        raise NotImplementedError

    def user_deleted(self, user_name: str) -> None:
        raise NotImplementedError

    def permission_created(self, permission: Permission) -> None:
        raise NotImplementedError

    def permission_deleted(self, permission: Permission) -> None:
        raise NotImplementedError

    def resync(self) -> None:
        # FIXME: this should be implemented in the eventual task addressing the resync mechanism.:
        raise NotImplementedError
