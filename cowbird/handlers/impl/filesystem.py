import os
import shutil
from typing import TYPE_CHECKING

from cowbird.handlers.handler import HANDLER_WORKSPACE_DIR_PARAM, Handler
from cowbird.utils import get_logger

if TYPE_CHECKING:
    from typing import Any

    # pylint: disable=W0611,unused-import
    from cowbird.typedefs import SettingsType

LOGGER = get_logger(__name__)

NOTEBOOKS_DIR_NAME = "notebooks"


class FileSystem(Handler):
    """
    Keep the proper directory structure in sync with the platform.
    """
    required_params = [HANDLER_WORKSPACE_DIR_PARAM]

    def __init__(self, settings, name, jupyterhub_user_data_dir, **kwargs):
        # type: (SettingsType, str, str, Any) -> None
        """
        Create the file system instance.

        :param settings: Cowbird settings for convenience
        :param name: Handler name
        :param jupyterhub_user_data_dir: Path to the JupyterHub user data directory,
                                         which will be symlinked to the working directory
        """
        super(FileSystem, self).__init__(settings, name, **kwargs)
        self.jupyterhub_user_data_dir = jupyterhub_user_data_dir

    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        raise NotImplementedError

    def _get_user_workspace_dir(self, user_name):
        return os.path.join(self.workspace_dir, user_name)

    def _get_jupyterhub_user_data_dir(self, user_name):
        return os.path.join(self.jupyterhub_user_data_dir, user_name)

    def user_created(self, user_name):
        user_workspace_dir = self._get_user_workspace_dir(user_name)
        try:
            os.mkdir(user_workspace_dir)
        except FileExistsError:
            LOGGER.info("User workspace directory already existing (skip creation): [%s]", user_workspace_dir)
        os.chmod(user_workspace_dir, 0o755)  # nosec
        create_symlink = False
        symlink_dir = os.path.join(user_workspace_dir, NOTEBOOKS_DIR_NAME)

        # Check if creating a new symlink is required
        if not os.path.islink(symlink_dir):
            if not os.path.exists(symlink_dir):
                create_symlink = True
            else:
                raise FileExistsError(f"Failed to create symlinked jupyterhub directory in the user {user_name}'s "
                                      "workspace, since a non-symlink directory already exists.")
        elif os.readlink(symlink_dir) != self._get_jupyterhub_user_data_dir(user_name):
            # If symlink already exists but points to the wrong source, update symlink to the new source directory.
            os.remove(symlink_dir)
            create_symlink = True

        if create_symlink:
            os.symlink(self._get_jupyterhub_user_data_dir(user_name), symlink_dir, target_is_directory=True)

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
