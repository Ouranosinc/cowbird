import functools
import os
import re
import stat
from time import sleep
from typing import Any, List, Optional, Protocol, Tuple, Union, cast, overload
from typing_extensions import TypeAlias

import requests
from celery import Task, chain, shared_task
from magpie.models import Layer, Workspace
from magpie.permissions import Access, Scope

from cowbird.handlers.handler import HANDLER_URL_PARAM, HANDLER_WORKSPACE_DIR_PARAM, Handler
from cowbird.handlers.handler_factory import HandlerFactory
from cowbird.handlers.impl.magpie import GEOSERVER_READ_PERMISSIONS, GEOSERVER_WRITE_PERMISSIONS
from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring
from cowbird.permissions_synchronizer import Permission
from cowbird.request_task import RequestTask
from cowbird.typedefs import JSON, SettingsType
from cowbird.utils import CONTENT_TYPE_JSON, get_logger, apply_default_path_ownership, apply_new_path_permissions

GeoserverType: TypeAlias = "Geoserver"  # need a reference for the decorator before it gets defined

# see https://github.com/sbdchd/celery-types
Task.__class_getitem__ = classmethod(lambda cls, *args, **kwargs: cls)


class GeoserverFuncSupportsWorkspace(Protocol):
    def __call__(  # type: ignore[misc]
        self: GeoserverType,
        *,
        workspace_name: str,
    ) -> requests.Response:
        ...


class GeoserverFuncSupportsDatastore(Protocol):
    def __call__(  # type: ignore[misc]
        self: GeoserverType,
        *,
        workspace_name: str,
        datastore_name: str,
        datastore_path: str,
    ) -> requests.Response:
        ...


class GeoserverFuncSupportsShapefile(Protocol):
    def __call__(  # type: ignore[misc]
        self: GeoserverType,
        *,
        workspace_name: str,
        datastore_name: str,
        filename: str,
    ) -> requests.Response:
        ...


GeoserverFunc = Union[
    GeoserverFuncSupportsWorkspace,
    GeoserverFuncSupportsDatastore,
    GeoserverFuncSupportsShapefile,
]

HANDLER_ADMIN_USER = "admin_user"  # nosec: B105
HANDLER_ADMIN_PASSWORD = "admin_password"  # nosec: B105

SHAPEFILE_MAIN_EXTENSION = ".shp"
SHAPEFILE_REQUIRED_EXTENSIONS = [SHAPEFILE_MAIN_EXTENSION, ".prj", ".dbf", ".shx"]
SHAPEFILE_OPTIONAL_EXTENSIONS = [".atx", ".sbx", ".qix", ".aih", ".ain", ".shp.xml", ".cpg"]
SHAPEFILE_ALL_EXTENSIONS = SHAPEFILE_OPTIONAL_EXTENSIONS + SHAPEFILE_REQUIRED_EXTENSIONS

DEFAULT_DATASTORE_DIR_NAME = "shapefile_datastore"

LOGGER = get_logger(__name__)


@overload
def geoserver_response_handling(func: GeoserverFuncSupportsWorkspace) -> GeoserverFuncSupportsWorkspace:
    ...


@overload
def geoserver_response_handling(func: GeoserverFuncSupportsDatastore) -> GeoserverFuncSupportsDatastore:
    ...


@overload
def geoserver_response_handling(func: GeoserverFuncSupportsShapefile) -> GeoserverFuncSupportsShapefile:
    ...


def geoserver_response_handling(func: GeoserverFunc) -> GeoserverFunc:
    """
    Decorator for response and logging handling for the different Geoserver HTTP requests.

    :param func: Function executing a http request to Geoserver
    :returns: Response object
    """

    @functools.wraps(func)
    def wrapper(geoserver: GeoserverType, **kwargs: str) -> requests.Response:

        # Geoserver responses are often full HTML pages for codes 400-499, so text/content is omitted from
        # the logs. Error responses in the 500-599 range are usually concise, so their text/content were included
        # in the logs to help eventual debugging.

        # This try/except is used to catch errors caused by an unavailable Geoserver instance.
        # Since a connection error causes the requests library to raise an exception (RequestException),
        # we can't rely on a response code and need to handle this case, so it can be seen in the logs.
        # Without this, the requests auto-retries as per RequestTask class's configurations.
        try:
            response = func(geoserver, **kwargs)  # type: ignore[arg-type,misc]  # since args are not named explicitly
        except Exception as error:
            LOGGER.error(error)
            raise requests.RequestException(f"Connection to Geoserver failed using [{geoserver.url}]")

        operation = func.__name__
        response_code = response.status_code
        fail_msg_intro = f"Operation [{operation}] failed"
        regex_exists = "Workspace &#39;.*&#39; already exists"
        regex_not_found = "Workspace &#39;.*&#39; not found"

        if response_code in (200, 201):
            LOGGER.info("Operation [%s] was successful.", operation)
        elif response_code == 401 and re.search(regex_exists, response.text):
            # This is done because Geoserver's reply/error code is misleading in this case and
            # returns HTML content.
            # LOGGER instead of GeoserverError because workspace existing should not block subsequent steps
            LOGGER.warning("Operation [%s] failed :Geoserver workspace already exists", operation)
        elif response_code == 401:
            raise GeoserverError(f"{fail_msg_intro} because it lacks valid authentication credentials.")
        elif response_code == 403 and operation == "_remove_workspace_request":
            raise GeoserverError(f"{fail_msg_intro} : Make sure `recurse` is set to `true` to delete workspace")
        elif response_code == 404 and re.search(regex_not_found, response.text):
            raise GeoserverError(f"{fail_msg_intro}: Geoserver workspace was not found")
        elif response_code == 404 and "No such data store" in response.text:
            raise GeoserverError(f"{fail_msg_intro} :Geoserver datastore was not found")
        elif response_code == 404 and "No such feature type" in response.text:
            raise GeoserverError(f"{fail_msg_intro} :Geoserver feature type was not found")
        elif response_code == 500:
            raise GeoserverError(f"{fail_msg_intro} : {response.text}")
        else:
            raise requests.RequestException(f"{fail_msg_intro} with HTTP error code [{response_code}]")

        return response

    return cast(GeoserverFunc, wrapper)


class Geoserver(Handler, FSMonitor):
    """
    Keep Geoserver internal representation in sync with the platform.
    """
    required_params = [HANDLER_URL_PARAM, HANDLER_WORKSPACE_DIR_PARAM]

    def __init__(self, settings: SettingsType, name: str, **kwargs: Any) -> None:
        """
        Create the geoserver handler instance.

        :param settings: Cowbird settings for convenience
        :param name: Handler name
        """
        super(Geoserver, self).__init__(settings, name, **kwargs)
        self.api_url = f"{self.url}/rest"
        self.headers = {"Content-type": CONTENT_TYPE_JSON}
        self.admin_user = kwargs.get(HANDLER_ADMIN_USER, None)
        self.admin_password = kwargs.get(HANDLER_ADMIN_PASSWORD, None)
        self.auth = (self.admin_user, self.admin_password)
        self.datastore_regex = rf"^{self.workspace_dir}/\w+/{DEFAULT_DATASTORE_DIR_NAME}/?$"

    #
    # Implementation of parent classes' functions
    #

    # Handler class functions
    def get_resource_id(self, resource_full_name: str) -> int:
        raise NotImplementedError

    def user_created(self, user_name: str) -> None:
        self._create_datastore_dir(user_name)
        res = chain(create_workspace.si(user_name), create_datastore.si(user_name))
        res.delay()
        LOGGER.info("Start monitoring datastore of created user [%s]", user_name)
        Monitoring().register(self._shapefile_folder_dir(user_name), True, Geoserver)

    def user_deleted(self, user_name: str) -> None:
        remove_workspace.delay(user_name)
        LOGGER.info("Stop monitoring datastore of created user [%s]", user_name)
        Monitoring().unregister(self._shapefile_folder_dir(user_name), self)

        # Attempt to delete the corresponding resources in Magpie
        magpie_handler = HandlerFactory().get_handler("Magpie")
        workspace_res_id = magpie_handler.get_geoserver_workspace_res_id(user_name)
        if not workspace_res_id:
            LOGGER.debug("No workspace resource named `%s` to delete in Magpie.", user_name)
        else:
            magpie_handler.delete_resource(workspace_res_id)

    def get_shapefile_list(self, workspace_name: str, shapefile_name: str) -> List[str]:
        """
        Generates the list of all files associated with a shapefile name.
        """
        base_filename = self._shapefile_folder_dir(workspace_name) + "/" + shapefile_name
        return [base_filename + ext for ext in SHAPEFILE_ALL_EXTENSIONS]

    def _update_resource_paths_permissions(self,
                                           resource_type: str,
                                           permission: Permission,
                                           resource_id: int,
                                           workspace_name: str,
                                           layer_name: Optional[str] = None,
                                           ) -> None:
        """
        Updates a single Magpie resource's associated paths according to its permissions found on Magpie.
        """
        if resource_type == Layer.resource_type_name:
            if not layer_name:
                raise GeoserverError("Missing layer name to update permissions.")
            path_list = self.get_shapefile_list(workspace_name, layer_name)
        else:
            path_list = [self._shapefile_folder_dir(workspace_name)]
        # Get the actual effective user permissions
        user_permissions = HandlerFactory().get_handler("Magpie").get_user_permissions_by_res_id(
            permission.user, resource_id, effective=True)

        allowed_user_perm_names = {p["name"] for p in user_permissions["permissions"]
                                   if p["access"] == Access.ALLOW.value}
        is_readable = any(p in GEOSERVER_READ_PERMISSIONS for p in allowed_user_perm_names)
        is_writable = any(p in GEOSERVER_WRITE_PERMISSIONS for p in allowed_user_perm_names)
        # Execute permissions are not required for shapefiles, so they will be disabled.
        # Execute permissions are always left enabled for directories.
        # If the workspace has a `Deny` read permission, only its read permission is disabled, blocking the access to
        # the directory's content via a file browser or in JupyterLab.
        # In the case the children resource also has an `Allow` read permission, the folder will not be browsable,
        # but the children resource will be kept accessible via a direct url or path.
        is_executable = resource_type == Workspace.resource_type_name

        for path in path_list:
            if not os.path.exists(path):
                if path.endswith(tuple(SHAPEFILE_REQUIRED_EXTENSIONS)):
                    LOGGER.warning("%s could not be found and its permissions could not be updated.", path)
                continue
            apply_new_path_permissions(path, is_readable, is_writable, is_executable)
            apply_default_path_ownership(path)

    def _update_resource_paths_permissions_recursive(self,
                                                     resource: JSON,
                                                     permission: Permission,
                                                     workspace_name: str,
                                                     ) -> None:
        """
        Recursive method to update all the path permissions of a resource and its children resources as found on Magpie.
        """
        resource_type: str = resource["resource_type"]
        if resource_type in [Workspace.resource_type_name, Layer.resource_type_name]:
            layer_name: str = resource["resource_name"] if resource_type == Layer.resource_type_name else None
            res_id: int = resource["resource_id"]
            self._update_resource_paths_permissions(resource_type=resource_type,
                                                    permission=permission,
                                                    resource_id=res_id,
                                                    workspace_name=workspace_name,
                                                    layer_name=layer_name)

        if permission.scope == Scope.RECURSIVE.value:
            for children_res in cast(JSON, resource["children"]).values():
                self._update_resource_paths_permissions_recursive(resource=children_res,
                                                                  permission=permission,
                                                                  workspace_name=workspace_name)

    def _update_permissions_on_filesystem(self, permission: Permission) -> None:
        """
        Updates the permissions of dir/files on the file system, after receiving a permission webhook event from Magpie.
        """
        if permission.name not in GEOSERVER_READ_PERMISSIONS + GEOSERVER_WRITE_PERMISSIONS:
            LOGGER.info("Nothing to do, since the permission `%s` is not specific to a Geoserver type service.",
                        permission.name)
            return

        magpie_handler = HandlerFactory().get_handler("Magpie")

        if permission.user is None:
            raise NotImplementedError("A permission change on a group is not supported for now on Geoserver, since "
                                      "workspaces are based on users only.")
        workspace_name = permission.user

        self._update_resource_paths_permissions_recursive(resource=magpie_handler.get_resource(permission.resource_id),
                                                          permission=permission,
                                                          workspace_name=workspace_name)

    def permission_created(self, permission: Permission) -> None:
        """
        Called when Magpie sends a permission created webhook event.
        """
        self._update_permissions_on_filesystem(permission)

    def permission_deleted(self, permission: Permission) -> None:
        """
        Called when Magpie sends a permission deleted webhook event.
        """
        self._update_permissions_on_filesystem(permission)

    # FSMonitor class functions
    @staticmethod
    def get_instance() -> Optional["Geoserver"]:
        """
        Return the Geoserver singleton instance from the class name used to retrieve the FSMonitor from the DB.
        """
        return HandlerFactory().get_handler("Geoserver")

    @staticmethod
    def publish_shapefile_task_chain(workspace_name: str, shapefile_name: str) -> None:
        """
        Applies the chain of tasks required to publish a new file to Geoserver.
        """
        res = chain(validate_shapefile.si(workspace_name, shapefile_name),
                    publish_shapefile.si(workspace_name, shapefile_name))
        res.delay()

    def on_created(self, path: str) -> None:
        """
        Call when a new path is found.

        :param path: Absolute path of a new file/directory
        """
        # Note that the workspace case is not implemented here, since a workspace directory is created during the user
        # creation (user_created()) and other directories should not be created manually for Geoserver.
        # The Magpie workspace resource will be automatically created if needed upon a shapefile creation.
        if path.endswith(SHAPEFILE_MAIN_EXTENSION):
            workspace_name, shapefile_name = self._get_shapefile_info(path)

            LOGGER.info("Starting Geoserver publishing process for [%s]", path)
            Geoserver.publish_shapefile_task_chain(workspace_name, shapefile_name)

            self._update_magpie_layer_permissions(workspace_name, shapefile_name)

    @staticmethod
    def remove_shapefile_task(workspace_name: str, shapefile_name: str) -> None:
        """
        Applies the celery task required to remove a shapefile from Geoserver.
        """
        remove_shapefile.delay(workspace_name, shapefile_name)

    def on_deleted(self, path: str) -> None:
        """
        Called when a path is deleted.

        :param path: Absolute path of a new file/directory
        """
        if os.path.isdir(path) and re.match(self.datastore_regex, path):
            # Note that the geoserver workspace and corresponding Magpie resources are only removed when the user is
            # deleted. The manual deletion of a datastore folder should be avoided.
            LOGGER.warning("An event was triggered for the deletion of the folder `%s`. The folder should "
                           "not be removed manually, but only when a user is deleted. This event invalidates the still "
                           "existing Geoserver workspace and corresponding Magpie resources.", path)
        elif path.endswith(SHAPEFILE_MAIN_EXTENSION):
            workspace_name, shapefile_name = self._get_shapefile_info(path)
            Geoserver.remove_shapefile_task(workspace_name, shapefile_name)

            # Remove all the remaining shapefile related files
            for file in self.get_shapefile_list(workspace_name, shapefile_name):
                if os.path.exists(file):
                    os.remove(file)

            # Remove the corresponding Magpie resource
            magpie_handler = HandlerFactory().get_handler("Magpie")
            layer_res_id = magpie_handler.get_geoserver_layer_res_id(workspace_name, shapefile_name)
            if layer_res_id:
                magpie_handler.delete_resource(layer_res_id)

    def on_modified(self, path: str) -> None:
        """
        Called when a path is updated.

        :param path: Absolute path of a new file/directory
        """
        # Nothing needs to be done specifically for Geoserver as Catalog already logs file modifications.
        # Only need to update permissions on Magpie, in case the resource permissions were modified.
        if os.path.isdir(path) and re.match(self.datastore_regex, path):
            workspace_name = path.split("/")[-2]
            self._update_magpie_workspace_permissions(workspace_name)
        elif path.endswith(SHAPEFILE_MAIN_EXTENSION):
            workspace_name, shapefile_name = self._get_shapefile_info(path)
            self._update_magpie_layer_permissions(workspace_name, shapefile_name)

    def resync(self) -> None:
        raise NotImplementedError

    @staticmethod
    def _is_permission_update_required(effective_permissions: List[JSON],
                                       user_name: str,
                                       res_id: int,
                                       perm_name: str,
                                       perm_access: str,
                                       perm_scope: str,
                                       delete_if_required: bool = False,
                                       ) -> bool:
        """
        Checks if the required permission already exists on the resource, else returns true if an update is required.

        Also, deletes the permission if the associated input argument is activated.
        """
        magpie_handler = HandlerFactory().get_handler("Magpie")
        actual_perms_on_resource: List[JSON] = []

        if perm_scope == Scope.RECURSIVE.value:
            # Special case for recursive permissions. We have to check the actual permission on the resource to verify
            # the actual scope.
            body: JSON = magpie_handler.get_user_permissions_by_res_id(user_name, res_id, effective=False)
            actual_perms_on_resource = cast(List[JSON], body["permissions"])

        for perm in effective_permissions:
            if perm["name"] == perm_name:
                if perm["access"] == perm_access and perm_scope == Scope.RECURSIVE.value:
                    # We truly have a valid recursive permission only if the resource has the actual recursive
                    # permission, or if the resource does not have the permission, which means the permission was
                    # inherited by the parent resources, which is a valid case, that doesn't need an update.
                    if (not any(p["name"] == perm_name for p in actual_perms_on_resource) or
                        any(p["name"] == perm_name and p["scope"] == Scope.RECURSIVE.value
                            for p in actual_perms_on_resource)):
                        return False
                elif perm["access"] == perm_access and perm["scope"] == perm_scope:
                    return False

                # Permission needs to be updated.
                if delete_if_required:
                    magpie_handler.delete_permission_by_user_and_res_id(user_name=user_name,
                                                                        res_id=res_id,
                                                                        permission_name=perm_name)
                break
        return True

    @staticmethod
    def _update_magpie_permissions(user_name: str,
                                   res_id: int,
                                   perm_scope: str,
                                   is_readable: bool,
                                   is_writable: bool,
                                   ) -> None:
        """
        Updates permissions on a Magpie resource (workspace/layer).
        """
        magpie_handler = HandlerFactory().get_handler("Magpie")

        allowed_perms = set(GEOSERVER_READ_PERMISSIONS if is_readable else [])
        allowed_perms = allowed_perms.union(GEOSERVER_WRITE_PERMISSIONS if is_writable else [])
        denied_perms = set(GEOSERVER_READ_PERMISSIONS + GEOSERVER_WRITE_PERMISSIONS).difference(allowed_perms)
        perm_names_and_access = ([(p, Access.ALLOW.value) for p in allowed_perms] +
                                 [(p, Access.DENY.value) for p in denied_perms])

        # Get resolved permissions on magpie
        user_perms_body: JSON = magpie_handler.get_user_permissions_by_res_id(user_name, res_id, effective=True)
        user_permissions = cast(List[JSON], user_perms_body["permissions"])

        perms_to_update = set()
        for perm_name, perm_access in perm_names_and_access:
            # Find all permissions that actually need an update. If the permission already exists but still needs an
            # update, delete the permission, and check in the next steps if the permission still needs an update
            # according to the new effective permission solving.
            if Geoserver._is_permission_update_required(effective_permissions=user_permissions,
                                                        user_name=user_name,
                                                        res_id=res_id,
                                                        perm_name=perm_name,
                                                        perm_access=perm_access,
                                                        perm_scope=perm_scope,
                                                        delete_if_required=True):
                perms_to_update.add((perm_name, perm_access))

        # Get new resolved permissions on magpie, after previous perms update were applied
        body: JSON = magpie_handler.get_user_permissions_by_res_id(user_name, res_id, effective=True)
        user_permissions = cast(List[JSON], body["permissions"])

        # Only apply new allow/deny permissions if required. If parent resources already have the required recursive
        # allow/deny, a new permission is not necessary and will not be created in order to simplify
        # effective permission solving.
        for perm_name, perm_access in perms_to_update:
            # No need to check the scope, since only `match` scopes are returned when getting `effective` permissions,
            # even if the permission comes from a `recursive` permission of a parent resource.
            if not any(p["name"] == perm_name and p["access"] == perm_access for p in user_permissions):
                magpie_handler.create_permission_by_user_and_res_id(
                    user_name=user_name,
                    res_id=res_id,
                    perm_name=perm_name,
                    perm_access=perm_access,
                    perm_scope=perm_scope)

    def _update_magpie_workspace_permissions(self, workspace_name: str) -> None:
        """
        Updates the permissions of a `workspace` resource on Magpie to the current permissions found on the
        corresponding datastore folder.
        """
        magpie_handler = HandlerFactory().get_handler("Magpie")
        workspace_res_id = magpie_handler.get_geoserver_workspace_res_id(workspace_name, create_if_missing=True)

        datastore_dir_path = self._shapefile_folder_dir(workspace_name)
        # Make sure the directory has the right ownership
        apply_default_path_ownership(datastore_dir_path)

        workspace_status = os.stat(datastore_dir_path)[stat.ST_MODE]
        is_readable = bool(workspace_status & stat.S_IROTH and workspace_status & stat.S_IXOTH)
        is_writable = bool(workspace_status & stat.S_IWOTH)

        self._update_magpie_permissions(user_name=workspace_name,
                                        res_id=workspace_res_id,
                                        perm_scope=Scope.RECURSIVE.value,
                                        is_readable=is_readable,
                                        is_writable=is_writable)

    def _update_magpie_layer_permissions(self, workspace_name: str, layer_name: str) -> None:
        """
        Updates the permissions of a `layer` resource on Magpie to the current permissions found on the corresponding
        shapefile.
        """
        magpie_handler = HandlerFactory().get_handler("Magpie")
        layer_res_id = magpie_handler.get_geoserver_layer_res_id(workspace_name, layer_name, create_if_missing=True)

        # Get permissions of the shapefile's main file
        is_readable, is_writable = self._get_shapefile_permissions(workspace_name, layer_name)
        self._normalize_shapefile_permissions(workspace_name, layer_name, is_readable, is_writable)
        self._update_magpie_permissions(user_name=workspace_name,
                                        res_id=layer_res_id,
                                        perm_scope=Scope.MATCH.value,
                                        is_readable=is_readable,
                                        is_writable=is_writable)

    #
    # Geoserver class specific functions
    #
    def create_workspace(self, name: str) -> None:
        """
        Create a new Geoserver workspace.

        :param name: Workspace name
        """
        LOGGER.info("Attempting to create Geoserver workspace [%s]", name)
        self._create_workspace_request(workspace_name=name)

    def remove_workspace(self, name: str) -> None:
        """
        Removes a workspace from geoserver. Will also remove all datastores associated with the workspace.

        :param name: Workspace name
        """
        LOGGER.info("Attempting to remove Geoserver workspace [%s]", name)
        self._remove_workspace_request(workspace_name=name)

    def create_datastore(self, workspace_name: str) -> None:
        """
        Create a new Geoserver workspace.

        :param self: Geoserver instance
        :param workspace_name: Workspace name where the datastore must be created
        """

        datastore_name = self._get_datastore_name(workspace_name)
        LOGGER.info("Creating datastore [%s] in geoserver workspace [%s]", datastore_name, workspace_name)

        self._create_datastore_request(workspace_name=workspace_name, datastore_name=datastore_name)
        datastore_path = self._geoserver_user_datastore_dir(workspace_name)
        self._configure_datastore_request(workspace_name=workspace_name,
                                          datastore_name=datastore_name,
                                          datastore_path=datastore_path)

    def publish_shapefile(self, workspace_name: str, shapefile_name: str) -> None:
        """
        Publish a shapefile in the specified workspace.

        :param workspace_name: Name of the workspace from which the shapefile will be published
        :param shapefile_name: The shapefile's name, without file extension
        """
        LOGGER.info("Shapefile [%s] is valid", shapefile_name)
        datastore_name = self._get_datastore_name(workspace_name)
        LOGGER.info("Attempting to publish shapefile [%s] to workspace:datastore [%s : %s]",
                    shapefile_name,
                    workspace_name,
                    datastore_name)
        self._publish_shapefile_request(workspace_name=workspace_name,
                                        datastore_name=datastore_name,
                                        filename=shapefile_name)

    def validate_shapefile(self, workspace_name: str, shapefile_name: str) -> None:
        """
        Validate shapefile.

        Will look for the three other files necessary for Geoserver publishing (.prj, .dbf, .shx)
        and raise a FileNotFoundError exception if one is missing.

        :param workspace_name: Name of the workspace from which the shapefile will be published
        :param shapefile_name: The shapefile's name, without file extension
        """
        # Small wait time to prevent unnecessary failure since shapefile is a multi file format
        sleep(1)
        files_to_find = [f"{self._shapefile_folder_dir(workspace_name)}/{shapefile_name}{ext}"
                         for ext in SHAPEFILE_REQUIRED_EXTENSIONS]
        for file in files_to_find:
            if not os.path.isfile(file):
                LOGGER.warning("Shapefile is incomplete: Missing [%s]", file)
                raise FileNotFoundError
        LOGGER.info("Shapefile [%s] is valid", shapefile_name)

    def _get_shapefile_permissions(self, workspace_name: str, shapefile_name: str) -> Tuple[bool, bool]:
        """
        Resolves the shapefile permissions on the file system, by checking the shapefile's main file permissions.
        """
        is_shapefile_readable = False
        is_shapefile_writable = False

        # Only consider the shapefile's main file for the permissions
        shapefile_path = self._shapefile_folder_dir(workspace_name) + "/" + shapefile_name + SHAPEFILE_MAIN_EXTENSION

        if os.path.exists(shapefile_path):
            file_status = os.stat(shapefile_path)[stat.ST_MODE]
            is_shapefile_readable = bool(file_status & stat.S_IROTH)
            is_shapefile_writable = bool(file_status & stat.S_IWOTH)
        return is_shapefile_readable, is_shapefile_writable

    def _normalize_shapefile_permissions(self,
                                         workspace_name: str,
                                         shapefile_name: str,
                                         is_readable: bool,
                                         is_writable: bool) -> None:
        """
        Makes sure all files associated with a shapefile is owned by the default user/group and have the same
        permissions.
        """
        for shapefile in self.get_shapefile_list(workspace_name, shapefile_name):
            if os.path.exists(shapefile):
                apply_default_path_ownership(shapefile)
                apply_new_path_permissions(shapefile,
                                           is_readable=is_readable,
                                           is_writable=is_writable,
                                           is_executable=False)

    def remove_shapefile(self, workspace_name: str, filename: str) -> None:
        """
        Remove a shapefile from the specified workspace.

        :param workspace_name: Name of the workspace from which the shapefile will be removed
        :param filename: The shapefile's name, without file extension
        """
        datastore_name = self._get_datastore_name(workspace_name)
        LOGGER.info("Attempting to remove shapefile [%s] from workspace:datastore [%s : %s]",
                    filename,
                    workspace_name,
                    datastore_name)
        self._remove_shapefile_request(workspace_name=workspace_name,
                                       datastore_name=datastore_name,
                                       filename=filename)

    #
    # Helper/request functions
    #
    # The following requests were built using Geoserver's REST documentation
    # https://docs.geoserver.org/master/en/user/rest/index.html
    #
    # As well as inspired by the following projects:
    # - https://github.com/gicait/geoserver-rest
    # - https://github.com/GeoNode/geoserver-restconfig
    #
    # While sometimes harder to get working, data payloads where written in json instead of xml as they are easier
    # to parse and use without external libraries.
    @staticmethod
    def _get_shapefile_info(filename: str) -> Tuple[str, str]:
        """
        :param filename: Relative filename of a new file
        :returns: Workspace name (str) where file is located and shapefile name (str)
        """
        split_path = filename.split("/")
        workspace = split_path[-3]
        shapefile_name, _ = split_path[-1].split(".")

        return workspace, shapefile_name

    @staticmethod
    def _get_datastore_name(workspace_name: str) -> str:
        """
        Return datastore name used to represent the datastore inside Geoserver.

        To be used in the HTTP requests sent to Geoserver.
        This name does not exist on the file system.
        """
        return f"shapefile_datastore_{workspace_name}"

    def _shapefile_folder_dir(self, workspace_name: str) -> str:
        """
        Returns the path to the user's shapefile datastore inside the file system.
        """
        return os.path.join(self.workspace_dir, workspace_name, DEFAULT_DATASTORE_DIR_NAME)

    @staticmethod
    def _geoserver_user_datastore_dir(user_name: str) -> str:
        """
        Returns the path to the user's shapefile datastore inside the Geoserver instance container.

        Uses the ``WORKSPACE_DIR`` env variable mapped in the Geoserver container.
        """
        return os.path.join("/user_workspaces", user_name, DEFAULT_DATASTORE_DIR_NAME)

    @geoserver_response_handling
    def _create_workspace_request(self, *, workspace_name: str) -> requests.Response:
        """
        Request to create a new workspace.

        :param workspace_name: Name of workspace to be created
        :returns: Response object
        """
        request_url = f"{self.api_url}/workspaces/"
        payload = {"workspace": {"name": workspace_name, "isolated": "True"}}
        response = requests.post(url=request_url, json=payload, auth=self.auth,
                                 headers=self.headers, timeout=self.timeout)
        return response

    @geoserver_response_handling
    def _remove_workspace_request(self,
                                  *,
                                  workspace_name: str,
                                  ) -> requests.Response:
        """
        Request to remove workspace and all associated datastores and layers.

        :param workspace_name: Name of workspace to remove
        :returns: Response object
        """
        request_url = f"{self.api_url}/workspaces/{workspace_name}?recurse=true"
        response = requests.delete(url=request_url, auth=self.auth,
                                   headers=self.headers, timeout=self.timeout)
        return response

    def _create_datastore_dir(self, workspace_name: str) -> None:
        datastore_folder_path = self._shapefile_folder_dir(workspace_name)
        try:
            os.mkdir(datastore_folder_path)
        except FileExistsError:
            LOGGER.info("User datastore directory already existing (skip creation): [%s]", datastore_folder_path)

    @geoserver_response_handling
    def _create_datastore_request(self,
                                  *,
                                  workspace_name: str,
                                  datastore_name: str,
                                  ) -> requests.Response:
        """
        Initial creation of the datastore with no connection parameters.

        :param workspace_name: Name of the workspace in which the datastore is created
        :param datastore_name: Name of the datastore that will be created
        :returns: Response object
        """
        request_url = f"{self.api_url}/workspaces/{workspace_name}/datastores"
        payload = {
            "dataStore": {
                "name": datastore_name,
                "type": "Directory of spatial files (shapefiles)",
                "connectionParameters": {
                    "entry": []
                },
            }
        }
        response = requests.post(url=request_url, json=payload, auth=self.auth,
                                 headers=self.headers, timeout=self.timeout)
        return response

    @geoserver_response_handling
    def _configure_datastore_request(self,
                                     *,
                                     workspace_name: str,
                                     datastore_name: str,
                                     datastore_path: str,
                                     ) -> requests.Response:
        """
        Configures the connection parameters of the datastore.

        This is done as a secondary step because Geoserver tends to create the wrong type of datastore
        (shapefile instead of directory of shapefiles) when setting them at creation.

        :param workspace_name: Name of the workspace in which the datastore is created
        :param datastore_name: Name of the datastore that will be created
        :returns: Response object
        """
        geoserver_datastore_path = f"file://{datastore_path}"
        request_url = f"{self.api_url}/workspaces/{workspace_name}/datastores/{datastore_name}"
        payload = {
            "dataStore": {
                "name": datastore_name,
                "type": "Directory of spatial files (shapefiles)",
                "connectionParameters": {
                    "entry": [
                        {"$": "UTF-8",
                         "@key": "charset"},
                        {"$": "shapefile",
                         "@key": "filetype"},
                        {"$": "true",
                         "@key": "create spatial index"},
                        {"$": "true",
                         "@key": "memory mapped buffer"},
                        {"$": "GMT",
                         "@key": "timezone"},
                        {"$": "true",
                         "@key": "enable spatial index"},
                        {"$": f"http://{datastore_name}",
                         "@key": "namespace"},
                        {"$": "true",
                         "@key": "cache and reuse memory maps"},
                        {"$": geoserver_datastore_path,
                         "@key": "url"},
                        {"$": "shape",
                         "@key": "fstype"},
                    ]
                },
            }
        }
        response = requests.put(url=request_url, json=payload, auth=self.auth,
                                headers=self.headers, timeout=self.timeout)
        return response

    @geoserver_response_handling
    def _publish_shapefile_request(self,
                                   *,
                                   workspace_name: str,
                                   datastore_name: str,
                                   filename: str,
                                   ) -> requests.Response:
        """
        Request to publish a shapefile in Geoserver. Does so by creating a `Feature type` in Geoserver.

        :param workspace_name: Workspace where file will be published
        :param datastore_name: Datastore where file will be published
        :param filename: Name of the shapefile (with no extensions)
        :returns: Response object
        """
        request_url = f"{self.api_url}/workspaces/{workspace_name}/datastores/{datastore_name}/featuretypes"

        # This is just a basic example. There are lots of other attributes that can be configured
        # https://docs.geoserver.org/latest/en/api/#1.0.0/featuretypes.yaml
        payload = {
            "featureType": {
                "name": filename,
                "nativeCRS": """
                                GEOGCS[
                                    "WGS 84", 
                                    DATUM[
                                        "World Geodetic System 1984",
                                        SPHEROID["WGS 84", 6378137.0, 298.257223563, AUTHORITY["EPSG","7030"]],
                                        AUTHORITY["EPSG","6326"]
                                    ],
                                    PRIMEM["Greenwich", 0.0, AUTHORITY["EPSG","8901"]],
                                    UNIT["degree", 0.017453292519943295],
                                    AXIS["Geodetic longitude", EAST],
                                    AXIS["Geodetic latitude", NORTH],
                                    AUTHORITY["EPSG","4326"]
                                ]
                            """,
                "srs": "EPSG:4326",
                "projectionPolicy": "REPROJECT_TO_DECLARED",
                "maxFeatures": 5000,
                "numDecimals": 6,
            }
        }
        response = requests.post(url=request_url, json=payload, auth=self.auth,
                                 headers=self.headers, timeout=self.timeout)
        return response

    @geoserver_response_handling
    def _remove_shapefile_request(self,
                                  *,
                                  workspace_name: str,
                                  datastore_name: str,
                                  filename: str,
                                  ) -> requests.Response:
        """
        Request to remove specified Geoserver `Feature type` and corresponding layer.

        :param workspace_name: Workspace where file is published
        :param datastore_name: Datastore where file is published
        :param filename: Name of the shapefile (with no extensions)
        :returns: Response object
        """
        request_url = (
            f"{self.api_url}/workspaces/{workspace_name}/datastores/{datastore_name}"
            f"/featuretypes/{filename}?recurse=true"
        )
        response = requests.delete(url=request_url, auth=self.auth,
                                   headers=self.headers, timeout=self.timeout)
        return response


@shared_task(bind=True, base=RequestTask, typing=True)
def create_workspace(_task: Task[[str], None], user_name: str) -> None:
    # Avoid any actual logic in celery task handler, only task related stuff should be done here
    return Geoserver.get_instance().create_workspace(user_name)


@shared_task(bind=True, base=RequestTask, typing=True)
def create_datastore(_task: Task[[str], None], datastore_name: str) -> None:
    # Avoid any actual logic in celery task handler, only task related stuff should be done here
    return Geoserver.get_instance().create_datastore(datastore_name)


@shared_task(bind=True, base=RequestTask, typing=True)
def remove_workspace(_task: Task[[str], None], workspace_name: str) -> None:
    # Avoid any actual logic in celery task handler, only task related stuff should be done here
    return Geoserver.get_instance().remove_workspace(workspace_name)


@shared_task(bind=True, autoretry_for=(FileNotFoundError,), retry_backoff=True, max_retries=8, typing=True)
def validate_shapefile(_task: Task[[Any, Any], None], workspace_name: str, shapefile_name: str) -> None:
    return Geoserver.get_instance().validate_shapefile(workspace_name, shapefile_name)


@shared_task(bind=True, base=RequestTask, typing=True)
def publish_shapefile(_task: Task[[Any, Any], None], workspace_name: str, shapefile_name: str) -> None:
    return Geoserver.get_instance().publish_shapefile(workspace_name, shapefile_name)


@shared_task(bind=True, base=RequestTask, typing=True)
def remove_shapefile(_task: Task[[Any, Any], None], workspace_name: str, shapefile_name: str) -> None:
    return Geoserver.get_instance().remove_shapefile(workspace_name, shapefile_name)


class GeoserverError(Exception):
    """
    Generic Geoserver error used to break request chains, as RequestTask only retries for a specific exception
    (RequestException).
    """
