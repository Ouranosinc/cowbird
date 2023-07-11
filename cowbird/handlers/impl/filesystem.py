import os
import re
import shutil
from typing import Any

from cowbird.handlers import HandlerFactory
from cowbird.handlers.handler import HANDLER_WORKSPACE_DIR_PARAM, Handler
from cowbird.permissions_synchronizer import Permission
from cowbird.typedefs import SettingsType
from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring
from cowbird.utils import get_logger

LOGGER = get_logger(__name__)

NOTEBOOKS_DIR_NAME = "notebooks"


class FileSystem(Handler, FSMonitor):
    """
    Keep the proper directory structure in sync with the platform.
    """
    required_params = [HANDLER_WORKSPACE_DIR_PARAM]

    def __init__(self,
                 settings: SettingsType,
                 name: str,
                 jupyterhub_user_data_dir: str,
                 wps_outputs_dir: str,
                 **kwargs: Any) -> None:
        """
        Create the file system instance.

        :param settings: Cowbird settings for convenience
        :param name: Handler name
        :param jupyterhub_user_data_dir: Path to the JupyterHub user data directory,
                                         which will be symlinked to the working directory
        :param wps_outputs_dir: Path to the wps outputs directory
        """
        super(FileSystem, self).__init__(settings, name, **kwargs)
        self.jupyterhub_user_data_dir = jupyterhub_user_data_dir

        # Make sure output path is normalized (e.g.: removing trailing slashes) to simplify regex usage
        self.wps_outputs_dir = os.path.normpath(wps_outputs_dir)

        # Regex to find any directory or file found in the `users` output path of a 'bird' service
        # {self.wps_outputs_dir}/<wps-bird-name>/users/<user-uuid>/...
        self.wps_outputs_users_regex = rf"^{self.wps_outputs_dir}/\w+/users/(\d+)/(.+)"

        if os.path.exists(self.wps_outputs_dir):
            LOGGER.info("Start monitoring wpsoutputs folder [%s]", self.wps_outputs_dir)
            Monitoring().register(self.wps_outputs_dir, True, self)
        else:
            # TODO: should this raise instead of only displaying a warning?
            LOGGER.warning("Failed to start monitoring on the wpsoutputs folder [%s]", self.wps_outputs_dir)

    def get_resource_id(self, resource_full_name: str) -> int:
        raise NotImplementedError

    def _get_user_workspace_dir(self, user_name: str) -> str:
        return os.path.join(self.workspace_dir, user_name)

    def _get_user_wps_outputs_dir(self, user_name):
        return os.path.join(self._get_user_workspace_dir(user_name), "wps_outputs/user")

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

    @staticmethod
    def get_instance():
        # type: () -> FileSystem
        """
        Return the FileSYstem singleton instance from the class name used to retrieve the FSMonitor from the DB.
        """
        return HandlerFactory().get_handler("FileSystem")

    def on_created(self, path):
        # type: (str) -> None
        """
        Call when a new path is found.

        :param path: Absolute path of a new file/directory
        """
        regex_match = re.search(self.wps_outputs_users_regex, path)
        if regex_match:
            user_id = int(regex_match.group(1))
            subpath = regex_match.group(2)

            magpie_handler = HandlerFactory().get_handler("Magpie")
            user_name = magpie_handler.get_user_name_from_user_id(user_id)
            user_workspace_dir = self._get_user_workspace_dir(user_name)

            if not os.path.exists(user_workspace_dir):
                raise FileNotFoundError(f"User {user_name} workspace not found at path {user_workspace_dir}. New wps"
                                        f"output {path} not added to the user workspace.")

            # TODO: special case for directory link, hardlink all the content? hardlinks are not possible on dirs
            # create hardlink in the user workspace (use corresponding dir or file path)
            hardlink_path = os.path.join(self._get_user_wps_outputs_dir(user_name), subpath)
            os.makedirs(os.path.dirname(hardlink_path))
            os.link(path, hardlink_path)
            # TODO: faire un check si le link est au bon fichier, sinon updater (un peu comme on faisait avec symlinks)

    def on_modified(self, path):
        # type: (str) -> None
        """
        Called when a path is updated.

        :param path: Absolute path of a new file/directory
        """
        # Nothing to do for files in the wps_outputs_dir, since hardlinks are updated automatically.
        pass

    def on_deleted(self, path):
        # type: (str) -> None
        """
        Called when a path is deleted.

        :param path: Absolute path of a new file/directory
        """
        pass

    def permission_created(self, permission: Permission) -> None:
        raise NotImplementedError

    def permission_deleted(self, permission: Permission) -> None:
        raise NotImplementedError
