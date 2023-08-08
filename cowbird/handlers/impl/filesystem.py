import os
import re
import shutil
from pathlib import Path
from typing import Any, List, Tuple, cast

from magpie.permissions import Access
from magpie.permissions import Permission as MagpiePermission
from magpie.services import ServiceAPI

from cowbird.handlers import HandlerFactory
from cowbird.handlers.handler import HANDLER_WORKSPACE_DIR_PARAM, Handler
from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring
from cowbird.permissions_synchronizer import Permission
from cowbird.typedefs import JSON, SettingsType
from cowbird.utils import apply_new_path_permissions, get_logger

LOGGER = get_logger(__name__)

NOTEBOOKS_DIR_NAME = "notebooks"
SECURE_DATA_PROXY_NAME = "secure-data-proxy"
USER_WPS_OUTPUTS_USER_DIR_NAME = "wpsoutputs"


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
        self.wps_outputs_user_data_regex = rf"^{self.wps_outputs_dir}/(\w+)/users/(\d+)/(.+)"

    def start_wpsoutputs_monitoring(self, monitoring: Monitoring) -> None:
        if os.path.exists(self.wps_outputs_dir):
            LOGGER.info("Start monitoring wpsoutputs folder [%s]", self.wps_outputs_dir)
            monitoring.register(self.wps_outputs_dir, True, self)
        else:
            LOGGER.warning("Input wpsoutputs folder [%s] does not exist.", self.wps_outputs_dir)

    def get_resource_id(self, resource_full_name: str) -> int:
        raise NotImplementedError

    def get_user_workspace_dir(self, user_name: str) -> str:
        return os.path.join(self.workspace_dir, user_name)

    def get_wps_outputs_user_dir(self, user_name: str) -> str:
        return os.path.join(self.get_user_workspace_dir(user_name), USER_WPS_OUTPUTS_USER_DIR_NAME)

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
        user_workspace_dir = self.get_user_workspace_dir(user_name)
        try:
            os.mkdir(user_workspace_dir)
        except FileExistsError:
            LOGGER.info("User workspace directory already existing (skip creation): [%s]", user_workspace_dir)
        os.chmod(user_workspace_dir, 0o755)  # nosec

        FileSystem._create_symlink_dir(src=self._get_jupyterhub_user_data_dir(user_name),
                                       dst=os.path.join(user_workspace_dir, NOTEBOOKS_DIR_NAME))

        # Create all hardlinks from the user wps outputs data
        for root, _, filenames in os.walk(self.wps_outputs_dir):
            for file in filenames:
                full_path = os.path.join(root, file)
                self._create_wpsoutputs_hardlink(src_path=full_path, overwrite=True,
                                                 process_user_files=True, process_public_files=False)

    def user_deleted(self, user_name: str) -> None:
        user_workspace_dir = self.get_user_workspace_dir(user_name)
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

    def get_user_hardlink(self, src_path: str, bird_name: str, user_name: str, subpath: str) -> str:
        user_workspace_dir = self.get_user_workspace_dir(user_name)
        if not os.path.exists(user_workspace_dir):
            raise FileNotFoundError(f"User {user_name} workspace not found at path {user_workspace_dir}. New "
                                    f"wpsoutput {src_path} not added to the user workspace.")

        subpath = os.path.join(bird_name, subpath)
        return os.path.join(self.get_wps_outputs_user_dir(user_name), subpath)

    def _get_secure_data_proxy_file_perms(self, src_path: str, user_name: str) -> Tuple[bool, bool]:
        """
        Finds a route from the `secure-data-proxy service` that matches the resource path (or one its parent resource)
        and gets the user permissions on that route.
        """
        magpie_handler = HandlerFactory().get_handler("Magpie")
        sdp_svc_info = magpie_handler.get_service_info("secure-data-proxy")
        # Find the closest related route resource
        expected_route = re.sub(rf"^{self.wps_outputs_dir}", "wpsoutputs", src_path)

        # Finds the resource id of the route matching the resource or the closest matching parent route.
        closest_res_id = None
        resource = magpie_handler.get_resource(cast(int, sdp_svc_info["resource_id"]))
        for segment in expected_route.split("/"):
            child_res_id = None
            for child in resource["children"].values():
                if child["resource_name"] == segment:
                    child_res_id = cast(int, child["resource_id"])
                    resource = child
                    break
            if not child_res_id:
                break
            closest_res_id = child_res_id

        if not closest_res_id:
            # No resource was found to be corresponding to even some part of the expected route.
            # Assume access is not allowed.
            is_readable = False
            is_writable = False
        else:
            # Resolve permissions
            res_perms = magpie_handler.get_user_permissions_by_res_id(user=user_name,
                                                                      res_id=closest_res_id,
                                                                      effective=True)["permissions"]
            read_access = [perm["access"] for perm in res_perms
                           if perm["name"] == MagpiePermission.READ.value][0]
            write_access = [perm["access"] for perm in res_perms
                            if perm["name"] == MagpiePermission.WRITE.value][0]
            is_readable = read_access == Access.ALLOW.value
            is_writable = write_access == Access.ALLOW.value
        return is_readable, is_writable

    def update_secure_data_proxy_path_perms(self, src_path: str, user_name: str) -> bool:
        """
        Gets a path's permissions from the secure-data-proxy service and updates the file system permissions
        accordingly.

        Returns a boolean to indicate if the user should have some type of access to the path or not.
        """
        is_readable, is_writable = self._get_secure_data_proxy_file_perms(src_path, user_name)
        apply_new_path_permissions(src_path, is_readable, is_writable, is_executable=False)

        access_allowed = True
        if not is_readable and not is_writable:
            # If no permission on the file, the hardlink should not be created.
            access_allowed = False
        return access_allowed

    @staticmethod
    def create_hardlink_path(src_path: str, hardlink_path: str, access_allowed: bool) -> None:
        """
        Creates a hardlink path from a source file, if the user has access rights.
        """
        if access_allowed:
            os.makedirs(os.path.dirname(hardlink_path), exist_ok=True)
            LOGGER.debug("Creating hardlink from file `%s` to the path `%s`", src_path, hardlink_path)
            try:
                os.link(src_path, hardlink_path)
            except Exception as exc:
                LOGGER.warning("Failed to create hardlink `%s` : %s", hardlink_path, exc)
        else:
            LOGGER.debug("Access to the wps output file `%s` is not allowed for the user. No hardlink created.",
                         src_path)

    def _create_wpsoutputs_hardlink(self, src_path: str, overwrite: bool = False,
                                    process_user_files: bool = True, process_public_files: bool = True) -> None:
        regex_match = re.search(self.wps_outputs_user_data_regex, src_path)
        access_allowed = True
        if regex_match:  # user files
            if not process_user_files:
                return

            magpie_handler = HandlerFactory().get_handler("Magpie")
            user_name = magpie_handler.get_user_name_from_user_id(int(regex_match.group(2)))
            hardlink_path = self.get_user_hardlink(src_path=src_path,
                                                   bird_name=regex_match.group(1),
                                                   user_name=user_name,
                                                   subpath=regex_match.group(3))
            api_services = magpie_handler.get_services_by_type(ServiceAPI.service_type)
            if SECURE_DATA_PROXY_NAME not in api_services:
                LOGGER.debug("`%s` service not found. Considering user wpsoutputs data as accessible by default.",
                             SECURE_DATA_PROXY_NAME)
                apply_new_path_permissions(src_path, True, True, False)
            else:  # get access and apply permissions if the secure-data-proxy exists
                access_allowed = self.update_secure_data_proxy_path_perms(src_path, user_name)
        else:  # public files
            if not process_public_files:
                return
            hardlink_path = self._get_public_hardlink(src_path)

        if os.path.exists(hardlink_path):
            if not overwrite and access_allowed:
                # Hardlink already exists, nothing to do.
                return
            # Delete the existing file at the destination path to reset the hardlink path with the expected source.
            LOGGER.warning("Removing existing hardlink destination path at `%s` to generate hardlink for the newly "
                           "created file.", hardlink_path)
            os.remove(hardlink_path)

        self.create_hardlink_path(src_path, hardlink_path, access_allowed)

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
        # Nothing to do for files in the wps_outputs folder.
        # Permission modifications (e.g.: via `chmod`) are not supported to simplify the management of wpsoutputs perms.
        # Any permission modifications should be done via Magpie, which will synchronize the permissions on any related
        # hardlinks automatically.

    def _delete_wpsoutputs_hardlink(self, src_path: str,
                                    process_user_files: bool = True, process_public_files: bool = True) -> bool:
        """
        Deletes the hardlink path that corresponds to the input source path.

        Returns a bool to indicate if a hardlink path was deleted or not.
        """
        regex_match = re.search(self.wps_outputs_user_data_regex, src_path)
        try:
            if regex_match:  # user paths
                if not process_user_files:
                    return False
                magpie_handler = HandlerFactory().get_handler("Magpie")
                user_name = magpie_handler.get_user_name_from_user_id(int(regex_match.group(2)))
                linked_path = self.get_user_hardlink(src_path=src_path,
                                                     bird_name=regex_match.group(1),
                                                     user_name=user_name,
                                                     subpath=regex_match.group(3))
            else:  # public paths
                if not process_public_files:
                    return False
                linked_path = self._get_public_hardlink(src_path)
            if os.path.isdir(linked_path):
                os.rmdir(linked_path)
            else:
                os.remove(linked_path)
            return True
        except FileNotFoundError:
            LOGGER.debug("No linked path to delete for the `on_deleted` event of the wpsoutput path `%s`.", src_path)
        return False

    def on_deleted(self, path: str) -> None:
        """
        Called when a path is deleted.

        :param path: Absolute path of a new file/directory
        """
        if Path(self.wps_outputs_dir) in Path(path).parents:
            LOGGER.info("Removing link associated to the deleted path `%s`", path)
            self._delete_wpsoutputs_hardlink(path)

    @staticmethod
    def _check_if_res_from_secure_data_proxy(res_tree: List[JSON]) -> bool:
        """
        Checks if the resource if part of a secure-data-proxy service of type API.
        """
        root_res_info = res_tree[0]
        if root_res_info["resource_name"] == SECURE_DATA_PROXY_NAME:
            svc_info = HandlerFactory().get_handler("Magpie").get_service_info(SECURE_DATA_PROXY_NAME)
            if svc_info["service_type"] == ServiceAPI.service_type:
                return True

        # No secure-data-proxy with the expected service type
        return False

    def _update_permissions_on_filesystem(self, permission: Permission) -> None:
        magpie_handler = HandlerFactory().get_handler("Magpie")
        res_tree = magpie_handler.get_parents_resource_tree(permission.resource_id)

        if self._check_if_res_from_secure_data_proxy(res_tree):
            full_route = self.wps_outputs_dir
            # Add subpath if the resource is a child of the main wpsoutputs resource
            if len(res_tree) > 2:
                child_route = "/".join(cast(List[str], [res["resource_name"] for res in res_tree[2:]]))
                full_route = os.path.join(full_route, child_route)

            # Find all users related to the permission
            if permission.user:
                users = {magpie_handler.get_user_id_from_user_name(permission.user): permission.user}
            else:
                # Find all users from the group
                users = {}
                for username in magpie_handler.get_user_names_by_group_name(permission.group):
                    users[magpie_handler.get_user_id_from_user_name(username)] = username

            # Find all contained user paths
            user_routes = {}
            if os.path.isfile(full_route):
                # use current route directly if it's a user data file
                regex_match = re.search(self.wps_outputs_user_data_regex, full_route)
                if regex_match and int(regex_match.group(2)) in users:
                    user_routes[full_route] = regex_match
            else:  # dir case, browse to find all children user file paths
                for root, _, filenames in os.walk(full_route):
                    for file in filenames:
                        full_path = os.path.join(root, file)
                        regex_match = re.search(self.wps_outputs_user_data_regex, full_path)
                        if regex_match and int(regex_match.group(2)) in users:
                            user_routes[full_path] = regex_match

            # Update permissions for all found user paths
            for user_path, path_regex_match in user_routes.items():
                user_name = users[int(path_regex_match.group(2))]
                access_allowed = self.update_secure_data_proxy_path_perms(user_path, user_name)
                try:
                    hardlink_path = self.get_user_hardlink(src_path=user_path,
                                                           bird_name=path_regex_match.group(1),
                                                           user_name=user_name,
                                                           subpath=path_regex_match.group(3))
                except FileNotFoundError:
                    LOGGER.debug("Failed to find a hardlink path corresponding to the source path [%s]. The user `%s` "
                                 "should already have an existing workspace.",
                                 user_path, user_name)
                    continue

                # Resync hardlink path
                if os.path.exists(hardlink_path):
                    os.remove(hardlink_path)
                self.create_hardlink_path(user_path, hardlink_path, access_allowed)

    def permission_created(self, permission: Permission) -> None:
        self._update_permissions_on_filesystem(permission)

    def permission_deleted(self, permission: Permission) -> None:
        self._update_permissions_on_filesystem(permission)

    def resync(self) -> None:
        """
        Resync operation, regenerating required links (user_workspace, wpsoutputs, ...)
        """
        LOGGER.info("Applying resync operation.")
        if not os.path.exists(self.wps_outputs_dir):
            LOGGER.warning("Skipping resync operation for wpsoutputs folder since the source folder `%s` could not be "
                           "found", self.wps_outputs_dir)
        else:
            # Delete the content of the linked public folder, but keep the folder to avoid breaking the volume
            # if the folder is mounted on a Docker container
            wps_outputs_public_dir = self.get_wps_outputs_public_dir()
            if not os.path.exists(wps_outputs_public_dir):
                LOGGER.debug("Linked public wps outputs data folder [%s] does not exist. "
                             "No public file to delete for the resync operation.", wps_outputs_public_dir)
            else:
                for filename in os.listdir(wps_outputs_public_dir):
                    file_path = os.path.join(wps_outputs_public_dir, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as exc:
                        LOGGER.error("Failed to delete path [%s] : %s", file_path, exc)

            # Delete wps outputs hardlinks for each user
            user_list = HandlerFactory().get_handler("Magpie").get_user_list()
            for user_name in user_list:
                shutil.rmtree(self.get_wps_outputs_user_dir(user_name), ignore_errors=True)

            # Create all hardlinks from files of the current source folder
            for root, _, filenames in os.walk(self.wps_outputs_dir):
                for file in filenames:
                    full_path = os.path.join(root, file)
                    self._create_wpsoutputs_hardlink(src_path=full_path, overwrite=True)
        # TODO: add resync of the user_workspace symlinks to the jupyterhub dirs,
        #   will be added during the resync task implementation
