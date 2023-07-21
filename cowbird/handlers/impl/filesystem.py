import os
import shutil
from typing import Any

from cowbird.handlers.handler import HANDLER_WORKSPACE_DIR_PARAM, Handler
from cowbird.permissions_synchronizer import Permission
from cowbird.typedefs import SettingsType
from cowbird.utils import get_logger

LOGGER = get_logger(__name__)

NOTEBOOKS_DIR_NAME = "notebooks"


class FileSystem(Handler):
    """
    Keep the proper directory structure in sync with the platform.
    """
    required_params = [HANDLER_WORKSPACE_DIR_PARAM]

    def __init__(self, settings: SettingsType, name: str, jupyterhub_user_data_dir: str, **kwargs: Any) -> None:
        """
        Create the file system instance.

        :param settings: Cowbird settings for convenience
        :param name: Handler name
        :param jupyterhub_user_data_dir: Path to the JupyterHub user data directory,
                                         which will be symlinked to the working directory
        """
        super(FileSystem, self).__init__(settings, name, **kwargs)
        self.jupyterhub_user_data_dir = jupyterhub_user_data_dir

    def get_resource_id(self, resource_full_name: str) -> int:
        raise NotImplementedError

    def _get_user_workspace_dir(self, user_name: str) -> str:
        return os.path.join(self.workspace_dir, user_name)

    def _get_jupyterhub_user_data_dir(self, user_name: str) -> str:
        return os.path.join(self.jupyterhub_user_data_dir, user_name)

    def user_created(self, user_name: str) -> None:
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
                                      "workspace, since a non-symlink directory already exists at the targeted path "
                                      f"{symlink_dir}.")
        elif os.readlink(symlink_dir) != self._get_jupyterhub_user_data_dir(user_name):
            # If symlink already exists but points to the wrong source, update symlink to the new source directory.
            os.remove(symlink_dir)
            create_symlink = True

        if create_symlink:
            os.symlink(self._get_jupyterhub_user_data_dir(user_name), symlink_dir, target_is_directory=True)

    def user_deleted(self, user_name: str) -> None:
        user_workspace_dir = self._get_user_workspace_dir(user_name)
        try:
            shutil.rmtree(user_workspace_dir)
        except FileNotFoundError:
            LOGGER.info("User workspace directory not found (skip removal): [%s]", user_workspace_dir)

    def permission_created(self, permission: Permission) -> None:
        raise NotImplementedError

    def permission_deleted(self, permission: Permission) -> None:
        raise NotImplementedError
