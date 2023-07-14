import os
import re
import shutil
from typing import Any
from pathlib import Path

from cowbird.handlers import HandlerFactory
from cowbird.handlers.handler import HANDLER_WORKSPACE_DIR_PARAM, Handler
from cowbird.permissions_synchronizer import Permission
from cowbird.typedefs import SettingsType
from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring
from cowbird.utils import get_logger

LOGGER = get_logger(__name__)

NOTEBOOKS_DIR_NAME = "notebooks"
USER_WPSOUTPUTS_USER_DIR_NAME = "wpsoutputs-user"


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

        # Make sure output path is normalized (e.g.: removing trailing slashes)
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

    def _get_wps_outputs_public_dir(self):
        return os.path.join(self.workspace_dir, "public/wpsoutputs")

    def _get_jupyterhub_user_data_dir(self, user_name: str) -> str:
        return os.path.join(self.jupyterhub_user_data_dir, user_name)

    @staticmethod
    def _create_symlink_dir(src: str, dst: str): -> None
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
    def get_instance():
        # type: () -> FileSystem
        """
        Return the FileSYstem singleton instance from the class name used to retrieve the FSMonitor from the DB.
        """
        return HandlerFactory().get_handler("FileSystem")

    def _create_wpsoutputs_hardlink(self, src_path, overwrite=False):
        regex_match = re.search(self.wps_outputs_users_regex, src_path)
        if regex_match:  # user files
            user_id = int(regex_match.group(1))
            subpath = regex_match.group(2)

            magpie_handler = HandlerFactory().get_handler("Magpie")
            user_name = magpie_handler.get_user_name_from_user_id(user_id)
            user_workspace_dir = self._get_user_workspace_dir(user_name)

            if not os.path.exists(user_workspace_dir):
                raise FileNotFoundError(f"User {user_name} workspace not found at path {user_workspace_dir}. New "
                                        f"wpsoutput {src_path} not added to the user workspace.")

            # TODO: faire le call à secure-data-proxy, remove link if exists and no permission,
            #  add link if doesn't exists and permission

            hardlink_path = os.path.join(self._get_user_wps_outputs_user_dir(user_name), subpath)
        else:  # public files
            subpath = os.path.relpath(src_path, self.wps_outputs_dir)
            hardlink_path = os.path.join(self._get_wps_outputs_public_dir(), subpath)

        if os.path.exists(hardlink_path):
            if not overwrite:
                # Hardlink already exists, nothing to do.
                return
            # Delete the existing file at the destination path to reset the hardlink path with the expected source.
            LOGGER.warning("Removing existing hardlink destination path at `%s` to generate hardlink for the newly"
                           "created file.", hardlink_path)
            os.remove(hardlink_path)

        os.makedirs(os.path.dirname(hardlink_path), exist_ok=True)
        os.link(src_path, hardlink_path)

    def on_created(self, path):
        # type: (str) -> None
        """
        Call when a new path is found.

        :param path: Absolute path of a new file/directory
        """
        if not os.path.isdir(path) and Path(self.wps_outputs_dir) in Path(path).parents:
            # Only process files, since hardlinks are not permitted on directories
            self._create_wpsoutputs_hardlink(src_path=path, overwrite=True)

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
        # TODO: If a file from wpsoutputs is deleted, make sure to delete the associated hardlink in the user workspace.
        #  No need to check secure-data-proxy. (maybe just check if # of links is > 1?, to avoid useless hardlink delete)
        pass

    def permission_created(self, permission: Permission) -> None:
        raise NotImplementedError

    def permission_deleted(self, permission: Permission) -> None:
        raise NotImplementedError
