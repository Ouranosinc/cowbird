from typing import TYPE_CHECKING

from cowbird.handlers.handler import Handler

if TYPE_CHECKING:
    from typing import Any

    # pylint: disable=W0611,unused-import
    from cowbird.typedefs import SettingsType


class Thredds(Handler):
    """
    Nothing to do right now.
    """
    required_params = []

    def __init__(self, settings, name, **kwargs):
        # type: (SettingsType, str, Any) -> None
        """
        Create the thredds instance.

        :param settings: Cowbird settings for convenience
        :param name: Handler name
        """
        super(Thredds, self).__init__(settings, name, **kwargs)

    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        raise NotImplementedError

    def user_created(self, user_name):
        raise NotImplementedError

    def user_deleted(self, user_name):
        raise NotImplementedError

    def permission_created(self, permission):
        raise NotImplementedError

    def permission_deleted(self, permission):
        raise NotImplementedError
