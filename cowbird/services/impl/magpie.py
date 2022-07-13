import time
from typing import TYPE_CHECKING

import requests
from pyramid.httpexceptions import HTTPError
from requests.cookies import RequestsCookieJar

from cowbird.config import ConfigError
from cowbird.permissions_synchronizer import PermissionSynchronizer
from cowbird.services.service import SERVICE_URL_PARAM, Service
from cowbird.utils import CONTENT_TYPE_JSON, get_logger

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional

    from cowbird.typedefs import SettingsType

LOGGER = get_logger(__name__)

COOKIES_TIMEOUT = 60


class Magpie(Service):
    """
    Complete the Magpie's webhook call by calling Magpie temporary urls. Also keep service-shared resources in sync when
    permissions are updated for one of them.

    ** Cowbird components diagram 1.2.0 needs to be update since Magpie can
    handle permissions synchronisation directly on permission update events. No
    need to handle them explicitly in nginx, thredds and geoserver classes.
    """
    required_params = [SERVICE_URL_PARAM]

    def __init__(self, settings, name, admin_user, admin_password, **kwargs):
        # type: (SettingsType, str, str, str, Any) -> None
        """
        Create the magpie instance and instantiate the permission synchronizer that will handle the permission events.

        :param settings: Cowbird settings for convenience
        :param name: Service name
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
        resp = requests.request(method=method, url=url, params=params, json=json, cookies=cookies, headers=self.headers)

        if resp.status_code in [401, 403]:
            # try refreshing cookies in case of Unauthorized or Forbidden error
            self.cookies = None
            cookies = self.login()
            resp = requests.request(method=method, url=url, params=params, json=json, cookies=cookies,
                                    headers=self.headers)
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
        # type (str) -> str
        raise NotImplementedError

    def get_resources_tree(self, resource_id):
        # type: (int) -> List
        """
        Returns the associated Magpie Resource object and all its parents in a list ordered from parent to child.
        """
        data = {"parent": "true", "invert": "true", "flatten": "true"}
        resp = self._send_request(method="GET", url=f"{self.url}/resources/{resource_id}", params=data)
        if resp.status_code != 200:
            raise RuntimeError("Could not find the input resource's parent resources.")
        return resp.json()["resources"]

    def get_user_permissions(self, user):
        # type: (str) -> Dict
        """
        Gets all user resource permissions.
        """
        resp = self._send_request(method="GET", url=f"{self.url}/users/{user}/resources")
        if resp.status_code != 200:
            raise RuntimeError(f"Could not find the user `{user}` resource permissions.")
        return resp.json()["resources"]

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

    def login(self):
        # type: () -> RequestsCookieJar
        """
        Login to Magpie app using admin credentials.
        """
        if not self.cookies or not self.last_cookies_update_time \
                or time.time() - self.last_cookies_update_time > COOKIES_TIMEOUT:
            data = {"user_name": self.admin_user, "password": self.admin_password}
            try:
                resp = requests.post(f"{self.url}/signin", json=data)
            except Exception as exc:
                raise RuntimeError(f"Failed to sign in to Magpie (url: `{self.url}`) with user `{self.admin_user}`. "
                                   f"Exception : {exc}. ")
            self.cookies = resp.cookies
            self.last_cookies_update_time = time.time()
        return self.cookies
