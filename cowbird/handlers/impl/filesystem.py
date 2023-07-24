import os
import re
import shutil
from pathlib import Path
from typing import Any

from cowbird.handlers import HandlerFactory
from cowbird.handlers.handler import HANDLER_WORKSPACE_DIR_PARAM, Handler
from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring
from cowbird.permissions_synchronizer import Permission
from cowbird.typedefs import SettingsType
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
        LOGGER.info("Creating Filesystem handler")
        super(FileSystem, self).__init__(settings, name, **kwargs)
        self.jupyterhub_user_data_dir = jupyterhub_user_data_dir

        self.wps_outputs_public_subdir = kwargs.get("wps_outputs_public_subdir", None)
        if not self.wps_outputs_public_subdir:
            # use default subdir if undefined or an empty string
            self.wps_outputs_public_subdir = "public/wpsoutputs"
        # Make sure output path is normalized for the regex (e.g.: removing trailing slashes)
        self.wps_outputs_dir = os.path.normpath(wps_outputs_dir)

        # Regex to find any directory or file found in the `users` output path of a 'bird' service
        # {self.wps_outputs_dir}/<wps-bird-name>/users/<user-uuid>/...
        self.wps_outputs_users_regex = rf"^{self.wps_outputs_dir}/\w+/users/(\d+)/(.+)"

    def start_wpsoutputs_monitoring(self, monitoring: Monitoring) -> None:
        if os.path.exists(self.wps_outputs_dir):
            LOGGER.info("Start monitoring wpsoutputs folder [%s]", self.wps_outputs_dir)
            monitoring.register(self.wps_outputs_dir, True, self)
        else:
            LOGGER.warning("Input wpsoutputs folder [%s] does not exist.", self.wps_outputs_dir)

    def get_resource_id(self, resource_full_name: str) -> int:
        raise NotImplementedError

    def _get_user_workspace_dir(self, user_name: str) -> str:
        return os.path.join(self.workspace_dir, user_name)

    def get_wps_outputs_public_dir(self) -> str:
        return os.path.join(self.workspace_dir, self.wps_outputs_public_subdir)

    def _get_jupyterhub_user_data_dir(self, user_name: str) -> str:
        return os.path.join(self.jupyterhub_user_data_dir, user_name)

    @staticmethod
    def _create_symlink_dir(src: str, dst: str) -> None:
        create_symlink = False

        # Check if creating a new symlink is required
        if not os.path.islink(dst):
            if not os.path.exists(dst):
                create_symlink = True
            else:
                raise FileExistsError("Failed to create symlinked directory, since a non-symlink directory already "
                                      f"exists at the targeted path {dst}.")
        elif os.readlink(dst) != src:
            # If symlink already exists but points to the wrong source, update symlink to the new source directory.
            os.remove(dst)
            create_symlink = True

        if create_symlink:
            os.symlink(src, dst, target_is_directory=True)

    def user_created(self, user_name: str) -> None:
        user_workspace_dir = self._get_user_workspace_dir(user_name)
        try:
            os.mkdir(user_workspace_dir)
        except FileExistsError:
            LOGGER.info("User workspace directory already existing (skip creation): [%s]", user_workspace_dir)
        os.chmod(user_workspace_dir, 0o755)  # nosec

        FileSystem._create_symlink_dir(src=self._get_jupyterhub_user_data_dir(user_name),
                                       dst=os.path.join(user_workspace_dir, NOTEBOOKS_DIR_NAME))

    def user_deleted(self, user_name: str) -> None:
        user_workspace_dir = self._get_user_workspace_dir(user_name)
        try:
            shutil.rmtree(user_workspace_dir)
        except FileNotFoundError:
            LOGGER.info("User workspace directory not found (skip removal): [%s]", user_workspace_dir)

    @staticmethod
    def get_instance() -> "FileSystem":
        """
        Return the FileSystem singleton instance from the class name used to retrieve the FSMonitor from the DB.
        """
        return HandlerFactory().get_handler("FileSystem")

    def _get_public_hardlink(self, src_path: str) -> str:
        subpath = os.path.relpath(src_path, self.wps_outputs_dir)
        return os.path.join(self.get_wps_outputs_public_dir(), subpath)

    def _create_wpsoutputs_hardlink(self, src_path: str, overwrite: bool = False) -> None:
        regex_match = re.search(self.wps_outputs_users_regex, src_path)
        if regex_match:  # user files  # pylint: disable=R1705,no-else-return
            return  # TODO: implement user hardlinks
        else:  # public files
            hardlink_path = self._get_public_hardlink(src_path)

        if os.path.exists(hardlink_path):
            if not overwrite:
                # Hardlink already exists, nothing to do.
                return
            # Delete the existing file at the destination path to reset the hardlink path with the expected source.
            LOGGER.warning("Removing existing hardlink destination path at `%s` to generate hardlink for the newly "
                           "created file.", hardlink_path)
            os.remove(hardlink_path)

        os.makedirs(os.path.dirname(hardlink_path), exist_ok=True)
        LOGGER.debug("Creating hardlink from file `%s` to the path `%s`", src_path, hardlink_path)
        try:
            os.link(src_path, hardlink_path)
        except Exception as exc:
            LOGGER.warning("Failed to create hardlink `%s` : %s", hardlink_path, exc)

    def on_created(self, path: str) -> None:
        """
        Call when a new path is found.

        :param path: Absolute path of a new file/directory
        """
        if not os.path.isdir(path) and Path(self.wps_outputs_dir) in Path(path).parents:
            # Only process files, since hardlinks are not permitted on directories
            LOGGER.info("Creating hardlink for the new file path `%s`", path)
            self._create_wpsoutputs_hardlink(src_path=path, overwrite=True)

    def on_modified(self, path: str) -> None:
        """
        Called when a path is updated.

        :param path: Absolute path of a new file/directory
        """
        # Nothing to do for files in the wps_outputs folder, since hardlinks are updated automatically.

    def on_deleted(self, path: str) -> None:
        """
        Called when a path is deleted.

        :param path: Absolute path of a new file/directory
        """
        if Path(self.wps_outputs_dir) in Path(path).parents:
            LOGGER.info("Removing link associated to the deleted path `%s`", path)
            regex_match = re.search(self.wps_outputs_users_regex, path)
            try:
                if regex_match:  # user paths  # pylint: disable=R1705,no-else-return
                    return  # TODO: implement user hardlinks
                else:  # public paths
                    linked_path = self._get_public_hardlink(path)
                if os.path.isdir(linked_path):
                    os.rmdir(linked_path)
                else:
                    os.remove(linked_path)
            except FileNotFoundError:
                LOGGER.debug("No linked path to delete for the `on_deleted` event of the wpsoutput path `%s`.", path)

    def permission_created(self, permission: Permission) -> None:
        raise NotImplementedError

    def permission_deleted(self, permission: Permission) -> None:
        raise NotImplementedError

    def resync(self) -> None:
        """
        Resync operation, regenerating required links (user_workspace, wpsoutputs, ...)
        """
        LOGGER.info("Applying resync operation.")
        if not os.path.exists(self.wps_outputs_dir):
            LOGGER.warning("Skipping resync operation for wpsoutputs folder since the source folder `%s` could not be "
                           "found", self.wps_outputs_dir)
        else:
            # Delete the linked public folder
            shutil.rmtree(self.get_wps_outputs_public_dir(), ignore_errors=True)

            # TODO: remove the users hardlinks to wpsoutputs too

            # Create all hardlinks from files of the current source folder
            for root, _, filenames in os.walk(self.wps_outputs_dir):
                for file in filenames:
                    full_path = os.path.join(root, file)
                    self._create_wpsoutputs_hardlink(src_path=full_path, overwrite=True)
        # TODO: add resync of the user_workspace symlinks to the jupyterhub dirs,
        #  will be added during the resync task implementation
