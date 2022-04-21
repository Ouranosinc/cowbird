from typing import TYPE_CHECKING

from cowbird.services.service import Service

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from cowbird.typedefs import SettingsType


class Nginx(Service):
    """
    Nothing to do right now.
    """
    required_params = []

    def __init__(self, settings, name, **kwargs):
        # type: (SettingsType, str, dict) -> None
        """
        Create the nginx instance.

        :param settings: Cowbird settings for convenience
        :param name: Service name
        """
        super(Nginx, self).__init__(settings, name, **kwargs)

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
