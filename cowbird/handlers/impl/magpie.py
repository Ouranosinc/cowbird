import time
from typing import Any, Dict, List, Optional, Union

import requests
from magpie.models import Layer, Workspace
from magpie.permissions import Permission
from magpie.services import ServiceGeoserver
from pyramid.response import Response
from requests.cookies import RequestsCookieJar

from cowbird.config import ConfigError
from cowbird.handlers.handler import HANDLER_URL_PARAM, Handler
from cowbird.permissions_synchronizer import PermissionSynchronizer
from cowbird.typedefs import JSON, PermissionActionType, PermissionConfigItemType, SettingsType
from cowbird.utils import CONTENT_TYPE_JSON, get_logger

LOGGER = get_logger(__name__)

COOKIES_TIMEOUT = 60

WFS_READ_PERMISSIONS = [Permission.DESCRIBE_FEATURE_TYPE.value,
                        Permission.DESCRIBE_STORED_QUERIES.value,
                        Permission.GET_CAPABILITIES.value,
                        Permission.GET_FEATURE.value,
                        Permission.GET_GML_OBJECT.value,
                        Permission.GET_PROPERTY_VALUE.value,
                        Permission.LIST_STORED_QUERIES.value]
WFS_WRITE_PERMISSIONS = [Permission.CREATE_STORED_QUERY.value,
                         Permission.DROP_STORED_QUERY.value,
                         Permission.GET_FEATURE_WITH_LOCK.value,
                         Permission.LOCK_FEATURE.value,
                         Permission.TRANSACTION.value]
WMS_READ_PERMISSIONS = [Permission.DESCRIBE_LAYER.value,
                        Permission.GET_CAPABILITIES.value,
                        Permission.GET_FEATURE_INFO.value,
                        Permission.GET_LEGEND_GRAPHIC.value,
                        Permission.GET_MAP.value]
WPS_READ_PERMISSIONS = [Permission.DESCRIBE_PROCESS.value, Permission.GET_CAPABILITIES.value]
WPS_WRITE_PERMISSIONS = [Permission.EXECUTE.value]

GEOSERVER_READ_PERMISSIONS = WFS_READ_PERMISSIONS + WMS_READ_PERMISSIONS
GEOSERVER_WRITE_PERMISSIONS = WFS_WRITE_PERMISSIONS


class Magpie(Handler):
    """
    Complete the Magpie's webhook call by calling Magpie temporary urls. Also keep service-shared resources in sync when
    permissions are updated for one of them.

    ** Cowbird components diagram 1.2.0 needs to be updated since Magpie can
    handle permissions synchronisation directly on permission update events. No
    need to handle them explicitly in nginx, thredds and geoserver classes.
    """
    required_params = [HANDLER_URL_PARAM]

    def __init__(self, settings: SettingsType, name: str, admin_user: str, admin_password: str, **kwargs: Any) -> None:
        """
        Create the magpie instance and instantiate the permission synchronizer that will handle the permission events.

        :param settings: Cowbird settings for convenience
        :param name: Handler name
        :param admin_user: Magpie admin username used for login.
        :param admin_password: Magpie admin password used for login.
        """
        super(Magpie, self).__init__(settings, name, **kwargs)

        self.headers = {"Content-type": CONTENT_TYPE_JSON}
        self.admin_user = admin_user
        self.admin_password = admin_password
        if not self.admin_user or not self.admin_password:
            raise ConfigError("Missing Magpie credentials in config. Admin Magpie username and password are required.")
        self.service_types = None
        self.cookies = None
        self.last_cookies_update_time = None

        self.permissions_synch = PermissionSynchronizer(self)

    def _send_request(self,
                      method: str,
                      url: str,
                      params: Optional[Any] = None,
                      json: Optional[Any] = None,
                      ) -> requests.Response:
        """
        Wrapping function to send requests to Magpie, which also handles login and cookies.
        """
        cookies = self.login()
        resp = requests.request(method=method, url=url, params=params, json=json,
                                cookies=cookies, headers=self.headers, timeout=self.timeout)

        if resp.status_code in [401, 403]:
            # try refreshing cookies in case of Unauthorized or Forbidden error
            self.cookies = None
            cookies = self.login()
            resp = requests.request(method=method, url=url, params=params, json=json,
                                    cookies=cookies, headers=self.headers, timeout=self.timeout)
        return resp

    def get_service_types(self) -> List[str]:
        """
        Returns the list of service types available on Magpie.
        """
        if not self.service_types:
            resp = self._send_request(method="GET", url=f"{self.url}/services/types")
            if resp.status_code != 200:
                raise MagpieHttpError("Could not get Magpie's service types. "
                                      f"HttpError {resp.status_code} : {resp.text}")
            self.service_types = list(resp.json()["service_types"])
        return self.service_types

    def get_services_by_type(self, service_type: str) -> Dict[str, JSON]:
        resp = self._send_request(method="GET", url=f"{self.url}/services/types/{service_type}")
        if resp.status_code != 200:
            raise MagpieHttpError(f"Failed to get the services of type `{service_type}`. "
                                  f"HttpError {resp.status_code} : {resp.text}")
        return resp.json()["services"][service_type]

    def get_service_info(self, service_name: str) -> Dict[str, JSON]:
        resp = self._send_request(method="GET", url=f"{self.url}/services/{service_name}")
        if resp.status_code != 200:
            raise MagpieHttpError(f"Could not find the `{service_name}` service info. "
                                  f"HttpError {resp.status_code} : {resp.text}")
        return resp.json()["service"]

    def get_resources_by_service(self, service_name: str) -> Dict[str, JSON]:
        resp = self._send_request(method="GET", url=f"{self.url}/services/{service_name}/resources")
        if resp.status_code != 200:
            raise MagpieHttpError(f"Could not find the `{service_name}` service's resources. "
                                  f"HttpError {resp.status_code} : {resp.text}")
        return resp.json()[service_name]

    def get_parents_resource_tree(self, resource_id: int) -> List[JSON]:
        """
        Returns the associated Magpie Resource object and all its parents in a list ordered from parent to child.
        """
        data = {"parent": "true", "invert": "true", "flatten": "true"}
        resp = self._send_request(method="GET", url=f"{self.url}/resources/{resource_id}", params=data)
        if resp.status_code != 200:
            raise MagpieHttpError(f"Could not find the parent resources of the resource id `{resource_id}`. "
                                  f"HttpError {resp.status_code} : {resp.text}")
        return resp.json()["resources"]

    def get_resource(self, resource_id: int) -> Dict[str, JSON]:
        """
        Returns the associated Magpie Resource object.
        """
        resp = self._send_request(method="GET", url=f"{self.url}/resources/{resource_id}", params={"parent": "false"})
        if resp.status_code != 200:
            raise MagpieHttpError(f"Could not find the resource with the id `{resource_id}. "
                                  f"HttpError {resp.status_code} : {resp.text}")
        return resp.json()["resource"]

    def get_geoserver_workspace_res_id(self,
                                       workspace_name: str,
                                       create_if_missing: Optional[bool] = False,
                                       ) -> Optional[int]:
        """
        Finds the resource id of a workspace resource from the `geoserver` type services.
        """
        workspace_res_id: Optional[int] = None
        geoserver_type_services = self.get_services_by_type(ServiceGeoserver.service_type)
        if not geoserver_type_services:
            raise ValueError(f"No service of type `{ServiceGeoserver.service_type}` found on Magpie while trying to get"
                             f" the workspace resource `{workspace_name}`.")
        for svc in geoserver_type_services.values():
            svc_res_id: int = svc["resource_id"]
            svc_children: JSON = self.get_resource(svc_res_id)["children"]
            for workspace in svc_children.values():
                if workspace["resource_name"] == workspace_name:
                    workspace_res_id = workspace["resource_id"]
        if not workspace_res_id and create_if_missing:
            parent_res_id: int = list(geoserver_type_services.values())[0]["resource_id"]
            workspace_res_id = self.create_resource(
                resource_name=workspace_name,
                resource_type=Workspace.resource_type_name,
                parent_id=parent_res_id)
        return workspace_res_id

    def get_geoserver_layer_res_id(self, workspace_name: str, layer_name: str, create_if_missing: bool = False) -> int:
        """
        Tries to get the resource id of a specific layer, on `geoserver` type services, and if requested, creates the
        resource and workspace if they do not exist yet.
        """
        layer_res_id: Optional[int] = None
        workspace_res_id: Optional[int] = None
        geoserver_type_services = self.get_services_by_type(ServiceGeoserver.service_type)
        if not geoserver_type_services:
            raise ValueError(f"No service of type `{ServiceGeoserver.service_type}` found on Magpie while trying to get"
                             f" the layer resource `{layer_name}`.")
        for svc in geoserver_type_services.values():
            if layer_res_id:
                break
            svc_res_id: int = svc["resource_id"]
            svc_children: JSON = self.get_resource(svc_res_id)["children"]
            for workspace in svc_children.values():
                if workspace["resource_name"] == workspace_name:
                    workspace_res_id = workspace["resource_id"]
                    for layer in workspace["children"].values():
                        if layer["resource_name"] == layer_name:
                            layer_res_id = layer["resource_id"]
                            break
                    break
        if not layer_res_id and create_if_missing:
            if not workspace_res_id:
                parent_res_id: int = list(geoserver_type_services.values())[0]["resource_id"]
                workspace_res_id = self.create_resource(
                    resource_name=workspace_name,
                    resource_type=Workspace.resource_type_name,
                    parent_id=parent_res_id)
            layer_res_id = self.create_resource(
                resource_name=layer_name,
                resource_type=Layer.resource_type_name,
                parent_id=workspace_res_id)
        return layer_res_id

    def get_user_list(self) -> List[str]:
        """
        Returns the list of all Magpie usernames.
        """
        resp = self._send_request(method="GET", url=f"{self.url}/users", params={"detail": False})
        if resp.status_code != 200:
            raise MagpieHttpError(f"Could not find the list of users. HttpError {resp.status_code} : {resp.text}")
        return resp.json()["user_names"]

    def get_user_id_from_user_name(self, user_name: str) -> int:
        """
        Finds the id of a user from his username.
        """
        resp = self._send_request(method="GET", url=f"{self.url}/users/{user_name}")
        if resp.status_code != 200:
            raise MagpieHttpError(f"Could not find the user `{user_name}`. HttpError {resp.status_code} : {resp.text}")
        return resp.json()["user"]["user_id"]

    def get_user_name_from_user_id(self, user_id: int) -> str:
        """
        Finds the name of a user from his user id.
        """
        resp = self._send_request(method="GET", url=f"{self.url}/users", params={"detail": True})
        if resp.status_code != 200:
            raise MagpieHttpError(f"Could not find the list of users. HttpError {resp.status_code} : {resp.text}")
        for user_info in resp.json()["users"]:
            if "user_id" in user_info and user_info["user_id"] == user_id:
                return user_info["user_name"]
        raise MagpieHttpError(f"Could not find any user with the id `{user_id}`.")

    def get_user_permissions(self, user: str) -> Dict[str, JSON]:
        """
        Gets all user resource permissions.
        """
        resp = self._send_request(method="GET", url=f"{self.url}/users/{user}/resources")
        if resp.status_code != 200:
            raise MagpieHttpError(f"Could not find the user `{user}` resource permissions. "
                                  f"HttpError {resp.status_code} : {resp.text}")
        return resp.json()["resources"]

    def get_user_permissions_by_res_id(self, user: str, res_id: int, effective: bool = False) -> Dict[str, JSON]:
        resp = self._send_request(method="GET", url=f"{self.url}/users/{user}/resources/{res_id}/permissions",
                                  params={"effective": effective})
        if resp.status_code != 200:
            raise MagpieHttpError(f"Could not find the user `{user}` permissions for the resource `{res_id}`. "
                                  f"HttpError {resp.status_code} : {resp.text}")
        return resp.json()

    def get_user_names_by_group_name(self, grp_name: str) -> List[str]:
        """
        Returns the list of Magpie usernames from a group.
        """
        resp = self._send_request(method="GET", url=f"{self.url}/groups/{grp_name}/users")
        if resp.status_code != 200:
            raise MagpieHttpError(f"Could not find the list of usernames from group `{grp_name}`. "
                                  f"HttpError {resp.status_code} : {resp.text}")
        return resp.json()["user_names"]

    def get_group_permissions(self, grp: str) -> Dict[str, JSON]:
        """
        Gets all group resource permissions.
        """
        resp = self._send_request(method="GET", url=f"{self.url}/groups/{grp}/resources")
        if resp.status_code != 200:
            raise MagpieHttpError(f"Could not find the group `{grp}` resource permissions. "
                                  f"HttpError {resp.status_code} : {resp.text}")
        return resp.json()["resources"]

    def get_group_permissions_by_res_id(self, grp: str, res_id: int, effective: bool = False) -> Dict[str, JSON]:
        resp = self._send_request(method="GET", url=f"{self.url}/groups/{grp}/resources/{res_id}/permissions",
                                  params={"effective": effective})
        if resp.status_code != 200:
            raise MagpieHttpError(f"Could not find the group `{grp}` permissions for the resource `{res_id}`. "
                                  f"HttpError {resp.status_code} : {resp.text}")
        return resp.json()

    def user_created(self, user_name: str) -> None:
        raise NotImplementedError

    def user_deleted(self, user_name: str) -> None:
        raise NotImplementedError

    def permission_created(self, permission: Permission) -> None:
        self.permissions_synch.create_permission(permission)

    def permission_deleted(self, permission: Permission) -> None:
        self.permissions_synch.delete_permission(permission)

    def resync(self) -> None:
        # FIXME: this should be implemented in the eventual task addressing the resync mechanism.
        raise NotImplementedError

    def create_permissions(self, permissions_data: List[PermissionConfigItemType]) -> None:
        """
        Make sure that the specified permissions exist on Magpie.
        """
        if permissions_data:
            action: PermissionActionType = "create"
            permissions_data[-1]["action"] = action

            resp = self._send_request(method="PATCH", url=f"{self.url}/permissions",
                                      json={"permissions": permissions_data})
            if resp.status_code == 200:
                LOGGER.info("Permission creation was successful.")
            else:
                raise MagpieHttpError(f"HttpError {resp.status_code} - Failed to create permissions : {resp.text}")
        else:
            LOGGER.warning("Empty permission data, no permissions to create.")

    def create_permission_by_res_id(self,
                                    res_id: int,
                                    perm_name: str,
                                    perm_access: str,
                                    perm_scope: str,
                                    user_name: Optional[str] = "",
                                    grp_name: Optional[str] = "",
                                    ) -> Union[Response, None]:

        if user_name:
            url = f"{self.url}/users/{user_name}/resources/{res_id}/permissions"
        elif grp_name:
            url = f"{self.url}/groups/{grp_name}/resources/{res_id}/permissions"
        else:
            raise ValueError("Trying to create a permission, but missing an input user name or group name.")

        resp = self._send_request(method="GET", url=url)
        if resp.status_code != 200:
            raise MagpieHttpError(f"HttpError {resp.status_code} - Failed to find resource: {resp.text}")

        # By default, POST to create a new permission, but check before if the permission already exists, to avoid
        # unnecessary events in Magpie.
        method = "POST"
        for perm in resp.json()["permissions"]:
            if perm["name"] == perm_name:
                if perm["access"] == perm_access and perm["scope"] == perm_scope:
                    LOGGER.debug("Similar permission already exist on resource for user/group.")
                    return None  # No request to apply
                # Permission already exists but an update is required to modify parameters
                method = "PUT"
                break

        permission_data = {
            "permission": {
                "name": perm_name,
                "access": perm_access,
                "scope": perm_scope,
            }
        }
        resp = self._send_request(method=method, url=url, json=permission_data)

        if resp.status_code in [200, 201]:
            LOGGER.info("Permission creation was successful.")
        else:
            raise MagpieHttpError(f"HttpError {resp.status_code} - Failed to create permission : {resp.text}")
        return resp

    def create_permission_by_user_and_res_id(self,
                                             user_name: str,
                                             res_id: int,
                                             perm_name: str,
                                             perm_access: str,
                                             perm_scope: str,
                                             ) -> Union[Response, None]:
        return self.create_permission_by_res_id(res_id=res_id,
                                                perm_name=perm_name,
                                                perm_access=perm_access,
                                                perm_scope=perm_scope,
                                                user_name=user_name)

    def create_permission_by_grp_and_res_id(self,
                                            grp_name: str,
                                            res_id: int,
                                            perm_name: str,
                                            perm_access: str,
                                            perm_scope: str,
                                            ) -> Union[Response, None]:
        return self.create_permission_by_res_id(res_id=res_id,
                                                perm_name=perm_name,
                                                perm_access=perm_access,
                                                perm_scope=perm_scope,
                                                grp_name=grp_name)

    def delete_permission_by_user_and_res_id(self, user_name: str, res_id: int, permission_name: str) -> None:
        resp = self._send_request(method="DELETE",
                                  url=f"{self.url}/users/{user_name}/resources/{res_id}/permissions/{permission_name}")
        if resp.status_code == 200:
            LOGGER.info("Permission deletion was successful.")
        elif resp.status_code == 404:
            LOGGER.debug("No permission found to delete.")
        else:
            raise MagpieHttpError(f"HttpError {resp.status_code} - Failed to delete permission : {resp.text}")

    def delete_permission_by_grp_and_res_id(self, grp_name: str, res_id: int, permission_name: str) -> None:
        resp = self._send_request(method="DELETE",
                                  url=f"{self.url}/groups/{grp_name}/resources/{res_id}/permissions/{permission_name}")
        if resp.status_code == 200:
            LOGGER.info("Permission deletion was successful.")
        elif resp.status_code == 404:
            LOGGER.debug("No permission found to delete.")
        else:
            raise MagpieHttpError(f"HttpError {resp.status_code} - Failed to delete permission : {resp.text}")

    def delete_permission(self, permissions_data: List[Dict[str, str]]) -> None:
        """
        Remove the specified permission from Magpie if it exists.
        """
        if permissions_data:
            permissions_data[-1]["action"] = "remove"

            resp = self._send_request(method="PATCH", url=f"{self.url}/permissions",
                                      json={"permissions": permissions_data})
            if resp.status_code == 200:
                LOGGER.info("Permission removal was successful.")
            else:
                raise MagpieHttpError(f"HttpError {resp.status_code} - Failed to remove permissions : {resp.text}")
        else:
            LOGGER.warning("Empty permission data, no permissions to remove.")

    def create_resource(self, resource_name: str, resource_type: str, parent_id: Optional[int],
                        resource_display_name: Optional[str] = None) -> int:
        """
        Creates the specified resource in Magpie and returns the created resource id if successful.
        """
        resource_data = {
            "resource_name": resource_name,
            "resource_display_name": resource_display_name or resource_name,
            "resource_type": resource_type,
            "parent_id": parent_id
        }
        resp = self._send_request(method="POST", url=f"{self.url}/resources", json=resource_data)
        if resp.status_code != 201:
            raise MagpieHttpError(f"HttpError {resp.status_code} - Failed to create resource : {resp.text}")
        LOGGER.info("Resource creation was successful.")
        return resp.json()["resource"]["resource_id"]

    def delete_resource(self, resource_id: int) -> None:
        resp = self._send_request(method="DELETE", url=f"{self.url}/resources/{resource_id}")
        if resp.status_code == 200:
            LOGGER.info("Delete resource successful.")
        elif resp.status_code == 404:
            LOGGER.info("Resource id was not found. No resource to delete.")
        else:
            raise MagpieHttpError(f"HttpError {resp.status_code} - Failed to delete resource : {resp.text}")

    def login(self) -> RequestsCookieJar:
        """
        Login to Magpie app using admin credentials.
        """
        if not self.cookies or not self.last_cookies_update_time \
                or time.time() - self.last_cookies_update_time > COOKIES_TIMEOUT:
            data = {"user_name": self.admin_user, "password": self.admin_password}
            try:
                resp = requests.post(f"{self.url}/signin", json=data, timeout=self.timeout)
            except Exception as exc:
                raise RuntimeError(f"Failed to sign in to Magpie (url: `{self.url}`) with user `{self.admin_user}`. "
                                   f"Exception : {exc}. ")
            self.cookies = resp.cookies
            self.last_cookies_update_time = time.time()
        return self.cookies


class MagpieHttpError(Exception):
    """
    Exception related to http requests done by the Magpie handler.
    """
