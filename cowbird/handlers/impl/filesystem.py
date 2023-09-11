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

DEFAULT_NOTEBOOKS_DIR_NAME = "notebooks"
DEFAULT_PUBLIC_WORKSPACE_WPS_OUTPUTS_SUBPATH = "public/wpsoutputs"
DEFAULT_SECURE_DATA_PROXY_NAME = "secure-data-proxy"
DEFAULT_USER_WPS_OUTPUTS_DIR_NAME = "wpsoutputs"


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
                 secure_data_proxy_name: str = DEFAULT_SECURE_DATA_PROXY_NAME,
                 notebooks_dir_name: str = DEFAULT_NOTEBOOKS_DIR_NAME,
                 public_workspace_wps_outputs_subpath: str = DEFAULT_PUBLIC_WORKSPACE_WPS_OUTPUTS_SUBPATH,
                 user_wps_outputs_dir_name: str = DEFAULT_USER_WPS_OUTPUTS_DIR_NAME,
                 **kwargs: Any) -> None:
        """
        Create the file system instance.

        :param settings: Cowbird settings for convenience
        :param name: Handler name
        :param jupyterhub_user_data_dir: Path to the JupyterHub user data directory,
                                         which will be symlinked to the working directory
        :param wps_outputs_dir: Path to the wps outputs directory
        :param secure_data_proxy_name: Name of the secure-data-proxy service found on Magpie
        :param notebooks_dir_name: Name of the symlink directory found in the user workspace and which directs to the
                                   user's notebook directory
        :param public_workspace_wps_outputs_subpath: Subpath to the directory containing hardlinks to the public WPS
                                                     outputs data
        :param user_wps_outputs_dir_name: Name of the directory found in the user workspace and which contains the
                                          hardlinks to the user WPS outputs data
        """
        LOGGER.info("Creating Filesystem handler")
        super(FileSystem, self).__init__(settings, name, **kwargs)

        self.jupyterhub_user_data_dir = jupyterhub_user_data_dir
        self.secure_data_proxy_name = secure_data_proxy_name
        # Make sure output path is normalized for the regex (e.g.: removing trailing slashes)
        self.wps_outputs_dir = os.path.normpath(wps_outputs_dir)
        self.notebooks_dir_name = notebooks_dir_name
        self.public_workspace_wps_outputs_subpath = public_workspace_wps_outputs_subpath
        self.user_wps_outputs_dir_name = user_wps_outputs_dir_name

        # Regex to find any directory or file found in the `users` output path of a 'bird' service
        # {self.wps_outputs_dir}/<wps-bird-name>/users/<user-uuid>/...
        self.wps_outputs_user_data_regex = re.compile(
            rf"^{self.wps_outputs_dir}/(?P<bird_name>\w+)/users/(?P<user_id>\d+)/(?P<subpath>.+)")

    def start_wpsoutputs_monitoring(self, monitoring: Monitoring) -> None:
        if os.path.exists(self.wps_outputs_dir):
            LOGGER.info("Start monitoring wpsoutputs folder [%s]", self.wps_outputs_dir)
            monitoring.register(self.wps_outputs_dir, True, self)
        else:
            LOGGER.warning("Input wpsoutputs folder [%s] does not exist.", self.wps_outputs_dir)

    def get_user_workspace_dir(self, user_name: str) -> str:
        return os.path.join(self.workspace_dir, user_name)

    def get_user_workspace_wps_outputs_dir(self, user_name: str) -> str:
        return os.path.join(self.get_user_workspace_dir(user_name), self.user_wps_outputs_dir_name)

    def get_public_workspace_wps_outputs_dir(self) -> str:
        return os.path.join(self.workspace_dir, self.public_workspace_wps_outputs_subpath)

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
                                      f"exists at the targeted path [{dst}].")
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
            LOGGER.info("User workspace directory already exists (skip creation): [%s]", user_workspace_dir)
        os.chmod(user_workspace_dir, 0o755)  # nosec

        FileSystem._create_symlink_dir(src=self._get_jupyterhub_user_data_dir(user_name),
                                       dst=os.path.join(user_workspace_dir, self.notebooks_dir_name))

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
        return os.path.join(self.get_public_workspace_wps_outputs_dir(), subpath)

    def get_user_hardlink(self, src_path: str, bird_name: str, user_name: str, subpath: str) -> str:
        user_workspace_dir = self.get_user_workspace_dir(user_name)
        if not os.path.exists(user_workspace_dir):
            raise FileNotFoundError(f"User `{user_name}` workspace not found at path [{user_workspace_dir}]. Failed to "
                                    f"find a hardlink path for the wpsoutput [{src_path}] source path.")
        subpath = os.path.join(bird_name, subpath)
        return os.path.join(self.get_user_workspace_wps_outputs_dir(user_name), subpath)

    def _get_secure_data_proxy_file_perms(self, src_path: str, user_name: str) -> Tuple[bool, bool]:
        """
        Finds a route from the `secure-data-proxy` service that matches the resource path (or one of its parent
        resource) and gets the user permissions on that route.
        """
        magpie_handler = HandlerFactory().get_handler("Magpie")
        sdp_svc_info = magpie_handler.get_service_info(self.secure_data_proxy_name)
        # Find the closest related route resource
        expected_route = re.sub(rf"^{self.wps_outputs_dir}", self.user_wps_outputs_dir_name, src_path)

        # Finds the resource id of the route or the closest matching parent route.
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
            # No resource corresponds to the expected route or one of its parent route.
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
        Gets a path's permissions from the `secure-data-proxy` service and updates the file system permissions
        accordingly.

        Returns a boolean to indicate if the user should have some type of access to the path or not.
        """
        is_readable, is_writable = self._get_secure_data_proxy_file_perms(src_path, user_name)

        # Files do not require the `executable` permission.
        apply_new_path_permissions(src_path, is_readable, is_writable, is_executable=False)

        access_allowed = True
        if not is_readable and not is_writable:
            # If no permission on the file, the hardlink should not be created.
            access_allowed = False
        return access_allowed

    @staticmethod
    def create_hardlink_path(src_path: str, hardlink_path: str, access_allowed: bool,
                             is_parent_dir_writable: bool = False) -> None:
        """
        Creates a hardlink path from a source file, if the user has access rights.
        """
        if access_allowed:
            os.makedirs(os.path.dirname(hardlink_path), exist_ok=True)

            # Set custom write permissions to the parent directory, since they are required for write permissive files
            # in JupyterLab.
            apply_new_path_permissions(os.path.dirname(hardlink_path),
                                       is_readable=True,
                                       is_writable=is_parent_dir_writable,
                                       is_executable=True)

            LOGGER.debug("Creating hardlink from file `%s` to the path `%s`", src_path, hardlink_path)
            try:
                os.link(src_path, hardlink_path)
            except Exception as exc:
                LOGGER.warning("Failed to create hardlink `%s` : %s", hardlink_path, exc)
        else:
            LOGGER.info("Access to the WPS output file `%s` is not allowed for the user. No hardlink created.",
                        src_path)

    def _create_wpsoutputs_hardlink(self, src_path: str, overwrite: bool = False,
                                    process_user_files: bool = True, process_public_files: bool = True) -> None:
        regex_match = self.wps_outputs_user_data_regex.search(src_path)
        access_allowed = True
        if regex_match:  # user files
            if not process_user_files:
                return

            # User workspace directories require write permissions to allow file modifications via JupyterLab for
            # files with write permissions
            is_parent_dir_writable = True

            magpie_handler = HandlerFactory().get_handler("Magpie")
            user_name = magpie_handler.get_user_name_from_user_id(int(regex_match.group("user_id")))
            hardlink_path = self.get_user_hardlink(src_path=src_path,
                                                   bird_name=regex_match.group("bird_name"),
                                                   user_name=user_name,
                                                   subpath=regex_match.group("subpath"))
            api_services = magpie_handler.get_services_by_type(ServiceAPI.service_type)
            if self.secure_data_proxy_name not in api_services:
                LOGGER.warning("`%s` service not found. Considering user wpsoutputs data as accessible by default.",
                               self.secure_data_proxy_name)
                apply_new_path_permissions(src_path, True, True, False)
            else:  # get access and apply permissions if the secure-data-proxy exists
                access_allowed = self.update_secure_data_proxy_path_perms(src_path, user_name)
        else:  # public files
            if not process_public_files:
                return
            is_parent_dir_writable = False  # public files are read-only
            hardlink_path = self._get_public_hardlink(src_path)

        if os.path.exists(hardlink_path):
            if not overwrite and access_allowed:
                # Hardlink already exists, nothing to do.
                return
            # Delete the existing file at the destination path to reset the hardlink path with the expected source.
            LOGGER.warning("Removing existing hardlink destination path at `%s` to generate hardlink for the newly "
                           "created file.", hardlink_path)
            os.remove(hardlink_path)

        self.create_hardlink_path(src_path, hardlink_path, access_allowed, is_parent_dir_writable)

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
        # Permission modifications (e.g.: via `chmod`) are not supported to simplify the management of wpsoutputs
        # permissions. Any permission modifications should be done via Magpie, which will synchronize the permissions on
        # any related hardlinks automatically.
        LOGGER.warning("Modification event detected on path [%s]. Event ignored as there is nothing to be done by the "
                       "handler.", path)

    def _delete_wpsoutputs_hardlink(self, src_path: str,
                                    process_user_paths: bool = True, process_public_paths: bool = True) -> bool:
        """
        Deletes the hardlink path that corresponds to the input source path.

        Returns a bool to indicate if a hardlink path was deleted or not.
        """
        regex_match = self.wps_outputs_user_data_regex.search(src_path)
        try:
            if regex_match:  # user paths
                if not process_user_paths:
                    return False
                magpie_handler = HandlerFactory().get_handler("Magpie")
                user_name = magpie_handler.get_user_name_from_user_id(int(regex_match.group("user_id")))
                linked_path = self.get_user_hardlink(src_path=src_path,
                                                     bird_name=regex_match.group("bird_name"),
                                                     user_name=user_name,
                                                     subpath=regex_match.group("subpath"))
            else:  # public paths
                if not process_public_paths:
                    return False
                linked_path = self._get_public_hardlink(src_path)
            if os.path.isdir(linked_path):
                shutil.rmtree(linked_path, ignore_errors=True)
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

    def _check_if_res_from_secure_data_proxy(self, res_tree: List[JSON]) -> bool:
        """
        Checks if the resource if part of a `secure-data-proxy` service of type API.
        """
        root_res_info = res_tree[0]
        if root_res_info["resource_name"] == self.secure_data_proxy_name:
            svc_info = HandlerFactory().get_handler("Magpie").get_service_info(self.secure_data_proxy_name)
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
            if len(res_tree) > 2:  # /secure-data-proxy/wpsoutputs/<subpath>
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
                regex_match = self.wps_outputs_user_data_regex.search(full_route)
                if regex_match and int(regex_match.group("user_id")) in users:
                    user_routes[full_route] = regex_match
            else:  # dir case, browse to find all children user file paths
                for root, _, filenames in os.walk(full_route):
                    for file in filenames:
                        full_path = os.path.join(root, file)
                        regex_match = self.wps_outputs_user_data_regex.search(full_path)
                        if regex_match and int(regex_match.group("user_id")) in users:
                            user_routes[full_path] = regex_match

            # Update permissions for all found user paths
            for user_path, path_regex_match in user_routes.items():
                user_name = users[int(path_regex_match.group("user_id"))]
                access_allowed = self.update_secure_data_proxy_path_perms(user_path, user_name)
                try:
                    hardlink_path = self.get_user_hardlink(src_path=user_path,
                                                           bird_name=path_regex_match.group("bird_name"),
                                                           user_name=user_name,
                                                           subpath=path_regex_match.group("subpath"))
                except FileNotFoundError:
                    LOGGER.warning("Failed to find a hardlink path corresponding to the source path [%s]. The user `%s`"
                                   " should already have an existing workspace.",
                                   user_path, user_name)
                    continue

                # Resync hardlink path
                if os.path.exists(hardlink_path):
                    os.remove(hardlink_path)
                self.create_hardlink_path(user_path, hardlink_path, access_allowed, is_parent_dir_writable=True)

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
            public_workspace_wps_outputs_dir = self.get_public_workspace_wps_outputs_dir()
            if not os.path.exists(public_workspace_wps_outputs_dir):
                LOGGER.debug("Linked public wps outputs data folder [%s] does not exist. "
                             "No public file to delete for the resync operation.", public_workspace_wps_outputs_dir)
            else:
                for filename in os.listdir(public_workspace_wps_outputs_dir):
                    file_path = os.path.join(public_workspace_wps_outputs_dir, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as exc:
                        LOGGER.error("Failed to delete path [%s].", file_path, exc_info=exc)

            # Delete wps outputs hardlinks for each user
            user_list = HandlerFactory().get_handler("Magpie").get_user_list()
            for user_name in user_list:
                shutil.rmtree(self.get_user_workspace_wps_outputs_dir(user_name), ignore_errors=True)

            # Create all hardlinks from files of the current source folder
            for root, _, filenames in os.walk(self.wps_outputs_dir):
                for file in filenames:
                    full_path = os.path.join(root, file)
                    self._create_wpsoutputs_hardlink(src_path=full_path, overwrite=True)
        # TODO: add resync of the user_workspace symlinks to the jupyterhub dirs,
        #   will be added during the resync task implementation
