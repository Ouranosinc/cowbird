import time
from typing import TYPE_CHECKING

import requests
from pyramid.httpexceptions import HTTPError
from requests.cookies import RequestsCookieJar

from cowbird.config import ConfigError
from cowbird.handlers.handler import HANDLER_URL_PARAM, Handler
from cowbird.permissions_synchronizer import PermissionSynchronizer
from cowbird.utils import CONTENT_TYPE_JSON, get_logger

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional

    from cowbird.typedefs import SettingsType

LOGGER = get_logger(__name__)

COOKIES_TIMEOUT = 60

WFS_READ_PERMISSIONS = ["describefeaturetype", "describestoredqueries", "getcapabilities", "getfeature", "getgmlobject",
                        "getpropertyvalue", "liststoredqueries"]
WFS_WRITE_PERMISSIONS = ["createstoredquery", "dropstoredquery", "getfeaturewithlock", "lockfeature", "transaction"]
WMS_READ_PERMISSIONS = ["describelayer", "getcapabilities", "getfeatureinfo", "getlegendgraphic", "getmap"]
WPS_READ_PERMISSIONS = ["describeprocess", "getcapabilities"]
WPS_WRITE_PERMISSIONS = ["execute"]

LAYER_READ_PERMISSIONS = WFS_READ_PERMISSIONS + WMS_READ_PERMISSIONS
LAYER_WRITE_PERMISSIONS = WFS_WRITE_PERMISSIONS


class Magpie(Handler):
    """
    Complete the Magpie's webhook call by calling Magpie temporary urls. Also keep service-shared resources in sync when
    permissions are updated for one of them.

    ** Cowbird components diagram 1.2.0 needs to be updated since Magpie can
    handle permissions synchronisation directly on permission update events. No
    need to handle them explicitly in nginx, thredds and geoserver classes.
    """
    required_params = [HANDLER_URL_PARAM]

    def __init__(self, settings, name, admin_user, admin_password, **kwargs):
        # type: (SettingsType, str, str, str, Any) -> None
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

    def _send_request(self, method, url, params=None, json=None):
        # type: (str, str, Optional[Any], Optional[Any]) -> requests.Response
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

    def get_service_types(self):
        # type: () -> List
        """
        Returns the list of service types available on Magpie.
        """
        if not self.service_types:
            resp = self._send_request(method="GET", url=f"{self.url}/services/types")
            if resp.status_code != 200:
                raise RuntimeError("Could not get Magpie's services.")
            self.service_types = list(resp.json()["service_types"])
        return self.service_types

    def get_resource_id(self, resource_full_name):
        # type: (str) -> str
        raise NotImplementedError

    def get_services_by_type(self, service_type):
        # type: (str) -> List
        resp = self._send_request(method="GET", url=f"{self.url}/services/types/{service_type}")
        if resp.status_code != 200:
            raise RuntimeError("Could not find the input type's services.")
        return resp.json()["services"][service_type]

    def get_resources_by_service(self, service_name):
        # type: (str) -> List
        resp = self._send_request(method="GET", url=f"{self.url}/services/{service_name}/resources")
        if resp.status_code != 200:
            raise RuntimeError("Could not find the input service's resources.")
        return resp.json()[service_name]

    def get_parents_resource_tree(self, resource_id):
        # type: (int) -> List
        """
        Returns the associated Magpie Resource object and all its parents in a list ordered from parent to child.
        """
        data = {"parent": "true", "invert": "true", "flatten": "true"}
        resp = self._send_request(method="GET", url=f"{self.url}/resources/{resource_id}", params=data)
        if resp.status_code != 200:
            raise RuntimeError("Could not find the input resource's parent resources.")
        return resp.json()["resources"]

    def get_children_resource_tree(self, resource_id):
        # type: (int) -> List
        """
        Returns the associated Magpie Resource object and all its children.
        """
        resp = self._send_request(method="GET", url=f"{self.url}/resources/{resource_id}", params={"parent": "false"})
        if resp.status_code != 200:
            raise RuntimeError("Could not find the input resource's children resources.")
        return resp.json()["resource"]["children"]

    def get_geoserver_resource_id(self, workspace_name, layer_name, create_if_missing=True):
        # type: (str, str, bool) -> int
        """
        Tries to get the resource id of a specific layer, on `geoserver` type services, and creates the resource and
        workspace if they do not exist yet.
        """
        layer_res_id, workspace_res_id = None, None
        geoserver_type_services = self.get_services_by_type("geoserver")
        if not geoserver_type_services:
            raise ValueError("No service of type `geoserver` found on Magpie while trying to get a layer resource id.")
        for svc in geoserver_type_services.values():
            if layer_res_id:
                break
            for workspace in self.get_children_resource_tree(svc["resource_id"]).values():
                if workspace["resource_name"] == workspace_name:
                    workspace_res_id = workspace["resource_id"]
                    for layer in workspace["children"].values():
                        if layer["resource_name"] == layer_name:
                            layer_res_id = layer["resource_id"]
                            break
                    break
        if not layer_res_id and create_if_missing:
            if not workspace_res_id:
                workspace_res_id = self.create_resource(
                    resource_name=workspace_name,
                    resource_type="workspace",
                    parent_id=list(geoserver_type_services.values())[0]["resource_id"])
            layer_res_id = self.create_resource(
                resource_name=layer_name,
                resource_type="layer",
                parent_id=workspace_res_id)
        return layer_res_id

    def create_user(self, user_name, email, password, group_name):
        resp = self._send_request(method="POST", url=f"{self.url}/users",
                                  json={
                                      "user_name": user_name,
                                      "email": email,
                                      "password": password,
                                      "group_name": group_name
                                  })
        if resp.status_code != 201:
            raise RuntimeError(f"Failed to create user `{user_name}`.")

    def delete_user(self, user_name):
        resp = self._send_request(method="DELETE", url=f"{self.url}/users/{user_name}")
        if resp.status_code == 200:
            LOGGER.info("Delete user successful.")
        elif resp.status_code == 404:
            LOGGER.info("User name was not found. No user to delete.")
        else:
            raise HTTPError(f"Failed to delete resource : {resp.text}")

    def get_user_permissions(self, user):
        # type: (str) -> Dict
        """
        Gets all user resource permissions.
        """
        resp = self._send_request(method="GET", url=f"{self.url}/users/{user}/resources")
        if resp.status_code != 200:
            raise RuntimeError(f"Could not find the user `{user}` resource permissions.")
        return resp.json()["resources"]

    def get_user_permissions_by_res_id(self, user, res_id, effective=False):
        # type: (str, int, bool) -> Dict
        resp = self._send_request(method="GET", url=f"{self.url}/users/{user}/resources/{res_id}/permissions",
                                  params={"effective": effective})
        if resp.status_code != 200:
            raise RuntimeError(f"Could not find the user `{user}` permissions for the resource `{res_id}`.")
        return resp.json()

    def get_group_permissions_by_res_id(self, grp, res_id, effective=False):
        # type: (str, int, bool) -> Dict
        resp = self._send_request(method="GET", url=f"{self.url}/groups/{grp}/resources/{res_id}/permissions",
                                  params={"effective": effective})
        if resp.status_code != 200:
            raise RuntimeError(f"Could not find the group `{grp}` permissions for the resource `{res_id}`.")
        return resp.json()

    def get_group_permissions(self, grp):
        # type: (str) -> Dict
        """
        Gets all group resource permissions.
        """
        resp = self._send_request(method="GET", url=f"{self.url}/groups/{grp}/resources")
        if resp.status_code != 200:
            raise RuntimeError(f"Could not find the group `{grp}` resource permissions.")
        return resp.json()["resources"]

    def user_created(self, user_name):
        raise NotImplementedError

    def user_deleted(self, user_name):
        raise NotImplementedError

    def permission_created(self, permission):
        self.permissions_synch.create_permission(permission)

    def permission_deleted(self, permission):
        self.permissions_synch.delete_permission(permission)

    def create_permission(self, permissions_data):
        # type: (List[Dict[str,str]]) -> None
        """
        Make sure that the specified permission exists on Magpie.
        """
        if permissions_data:
            permissions_data[-1]["action"] = "create"

            resp = self._send_request(method="PATCH", url=f"{self.url}/permissions",
                                      json={"permissions": permissions_data})
            if resp.status_code == 200:
                LOGGER.info("Permission creation was successful.")
            else:
                raise HTTPError(f"Failed to create permissions : {resp.text}")
        else:
            LOGGER.warning("Empty permission data, no permissions to create.")

    def create_permission_by_user_and_res_id(self, user_name, res_id, permission_data):
        # type: (str, int, Dict[str,Dict[str,str]]) -> None
        resp = self._send_request(method="POST", url=f"{self.url}/users/{user_name}/resources/{res_id}/permissions",
                                  json=permission_data)
        if resp.status_code == 201:
            LOGGER.info("Permission creation was successful.")
        elif resp.status_code == 409:
            LOGGER.info("Similar permission already exist on resource for user.")
        else:
            raise HTTPError(f"Failed to create permission : {resp.text}")

    def create_permission_by_grp_and_res_id(self, grp_name, res_id, permission_data):
        # type: (str, int, Dict[str,Dict[str,str]]) -> None
        resp = self._send_request(method="POST", url=f"{self.url}/groups/{grp_name}/resources/{res_id}/permissions",
                                  json=permission_data)
        if resp.status_code == 201:
            LOGGER.info("Permission creation was successful.")
        elif resp.status_code == 409:
            LOGGER.info("Similar permission already exist on resource for group.")
        else:
            raise HTTPError(f"Failed to create permission : {resp.text}")

    def delete_permission_by_user_and_res_id(self, user_name, res_id, permission_name):
        # type: (str, int, str) -> None
        resp = self._send_request(method="DELETE",
                                  url=f"{self.url}/users/{user_name}/resources/{res_id}/permissions/{permission_name}")
        if resp.status_code == 200:
            LOGGER.info("Permission deletion was successful.")
        elif resp.status_code == 404:
            LOGGER.info("No permission found to delete.")
        else:
            raise HTTPError(f"Failed to delete permission : {resp.text}")

    def delete_permission_by_grp_and_res_id(self, grp_name, res_id, permission_name):
        # type: (str, int, str) -> None
        resp = self._send_request(method="DELETE",
                                  url=f"{self.url}/groups/{grp_name}/resources/{res_id}/permissions/{permission_name}")
        if resp.status_code == 200:
            LOGGER.info("Permission deletion was successful.")
        elif resp.status_code == 404:
            LOGGER.info("No permission found to delete.")
        else:
            raise HTTPError(f"Failed to delete permission : {resp.text}")

    def delete_permission(self, permissions_data):
        # type: (List[Dict[str,str]]) -> None
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
                raise HTTPError(f"Failed to remove permissions : {resp.text}")
        else:
            LOGGER.warning("Empty permission data, no permissions to remove.")

    def create_resource(self, resource_name, resource_type, parent_id):
        # type: (str, str, int) -> int
        """
        Creates the specified resource in Magpie and returns the created resource id if successful.
        """
        resource_data = {
            "resource_name": resource_name,
            "resource_display_name": resource_name,
            "resource_type": resource_type,
            "parent_id": parent_id
        }
        resp = self._send_request(method="POST", url=f"{self.url}/resources", json=resource_data)
        if resp.status_code != 201:
            raise HTTPError(f"Failed to create resource : {resp.text}")
        LOGGER.info("Resource creation was successful.")
        return resp.json()["resource"]["resource_id"]

    def delete_resource(self, resource_id):
        resp = self._send_request(method="DELETE", url=f"{self.url}/resources/{resource_id}")
        if resp.status_code == 200:
            LOGGER.info("Delete resource successful.")
        elif resp.status_code == 404:
            LOGGER.info("Resource id was not found. No resource to delete.")
        else:
            raise HTTPError(f"Failed to delete resource : {resp.text}")

    def create_service(self, service_data):
        # type (Dict[str, str]) -> str
        resp = self._send_request(method="POST", url=f"{self.url}/services", json=service_data)
        if resp.status_code != 201:
            raise HTTPError(f"Failed to create service : {resp.text}")
        LOGGER.info("Service creation was successful.")
        return resp.json()["service"]["resource_id"]

    def delete_service(self, service_name):
        resp = self._send_request(method="DELETE", url=f"{self.url}/services/{service_name}")
        if resp.status_code == 200:
            LOGGER.info("Delete service successful.")
        elif resp.status_code == 404:
            LOGGER.info("Service name was not found. No service to delete.")
        else:
            raise HTTPError(f"Failed to delete resource : {resp.text}")

    def delete_all_services(self):
        resp = self._send_request(method="GET", url=f"{self.url}/services")
        if resp.status_code == 200:
            for services_by_svc_type in resp.json()["services"].values():
                for svc in services_by_svc_type.values():
                    self.delete_service(svc["service_name"])
        else:
            raise HTTPError("Failed to find Magpie services.")

    def login(self):
        # type: () -> RequestsCookieJar
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
