import os
import shutil
from typing import TYPE_CHECKING

from cowbird.services.service import SERVICE_WORKSPACE_DIR_PARAM, Service
from cowbird.utils import get_logger

if TYPE_CHECKING:
    from typing import Any

    # pylint: disable=W0611,unused-import
    from cowbird.typedefs import SettingsType

LOGGER = get_logger(__name__)


class FileSystem(Service):
    """
    Keep the proper directory structure in sync with the platform.
    """
    required_params = [SERVICE_WORKSPACE_DIR_PARAM]

    def __init__(self, settings, name, **kwargs):
        # type: (SettingsType, str, Any) -> None
        """
        Create the file system instance.

        :param settings: Cowbird settings for convenience
        :param name: Service name
        """
        super(FileSystem, self).__init__(settings, name, **kwargs)

    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        raise NotImplementedError

    def _get_user_workspace_dir(self, user_name):
        return os.path.join(self.workspace_dir, user_name)

    def user_created(self, user_name):
        user_workspace_dir = self._get_user_workspace_dir(user_name)
        try:
            os.mkdir(user_workspace_dir)
        except FileExistsError:
            LOGGER.info("User workspace directory already existing (skip creation): [%s]", user_workspace_dir)

    def user_deleted(self, user_name):
        user_workspace_dir = self._get_user_workspace_dir(user_name)
        try:
            shutil.rmtree(user_workspace_dir)
        except FileNotFoundError:
            LOGGER.info("User workspace directory not found (skip removal): [%s]", user_workspace_dir)

    def permission_created(self, permission):
        raise NotImplementedError

    def permission_deleted(self, permission):
        raise NotImplementedError
