from typing import TYPE_CHECKING

import requests
from pyramid.httpexceptions import HTTPError
from requests.cookies import RequestsCookieJar

from cowbird.config import ConfigError
from cowbird.permissions_synchronizer import PermissionSynchronizer
from cowbird.services.service import SERVICE_URL_PARAM, Service
from cowbird.utils import CONTENT_TYPE_JSON, get_logger

if TYPE_CHECKING:
    from typing import Dict, List

    from cowbird.typedefs import SettingsType

MAGPIE_ADMIN_USER_TAG = "admin_user"  # nosec: B105
MAGPIE_ADMIN_PASSWORD_TAG = "admin_password"  # nosec: B105

LOGGER = get_logger(__name__)


class Magpie(Service):
    """
    Complete the Magpie's webhook call by calling Magpie temporary urls. Also keep service-shared resources in sync when
    permissions are updated for one of them.

    ** Cowbird components diagram 1.2.0 needs to be update since Magpie can
    handle permissions synchronisation directly on permission update events. No
    need to handle them explicitly in nginx, thredds and geoserver classes.
    """
    required_params = [SERVICE_URL_PARAM]

    def __init__(self, settings, name, **kwargs):
        # type: (SettingsType, str, Dict) -> None
        """
        Create the magpie instance and instantiate the permission synchronizer that will handle the permission events.

        :param settings: Cowbird settings for convenience
        :param name: Service name
        """
        super(Magpie, self).__init__(settings, name, **kwargs)

        self.headers = {"Content-type": CONTENT_TYPE_JSON}
        self.admin_user = kwargs.get(MAGPIE_ADMIN_USER_TAG, None)
        self.admin_password = kwargs.get(MAGPIE_ADMIN_PASSWORD_TAG, None)
        if not self.admin_user or not self.admin_password:
            raise ConfigError("Missing Magpie credentials in config. Admin Magpie username and password are required.")
        self.auth = (self.admin_user, self.admin_password)

        self.permissions_synch = PermissionSynchronizer(self)

    def get_service_names(self):
        # type: () -> List
        """
        Returns the list of service names available on Magpie.
        """
        cookies = self.login()
        resp = requests.get(url=f"{self.url}/services", headers=self.headers, cookies=cookies)
        if resp.status_code != 200:
            raise RuntimeError("Could not get Magpie's services.")
        return list(resp.json()["services"].keys())

    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        raise NotImplementedError

    def get_resources_tree(self, resource_id):
        # type: (int) -> List
        """
        Returns the associated Magpie Resource object and all its parents in a list ordered from parent to child.
        """
        cookies = self.login()
        data = {"parent": "true", "invert": "true", "flatten": "true"}
        resp = requests.get(url=f"{self.url}/resources/{resource_id}",
                            headers=self.headers, cookies=cookies, params=data)
        if resp.status_code != 200:
            raise RuntimeError("Could not find the input resource's parent resources.")
        return resp.json()["resources"]

    def get_user_permissions(self, user):
        # type: (str) -> bool
        """
        Gets all user resource permissions.
        """
        cookies = self.login()
        resp = requests.get(url=f"{self.url}/users/{user}/resources",
                            headers=self.headers, cookies=cookies)
        if resp.status_code != 200:
            raise RuntimeError(f"Could not find the user `{user}` resource permissions.")
        return resp.json()["resources"]

    def get_group_permissions(self, grp):
        # type: (str) -> bool
        """
        Gets all group resource permissions.
        """
        cookies = self.login()
        resp = requests.get(url=f"{self.url}/groups/{grp}/resources",
                            headers=self.headers, cookies=cookies)
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
        cookies = self.login()

        if permissions_data:
            permissions_data[-1]["action"] = "create"

            resp = requests.patch(
                url=f"{self.url}/permissions",
                headers=self.headers, cookies=cookies, json={"permissions": permissions_data}
            )
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
        cookies = self.login()
        if permissions_data:
            permissions_data[-1]["action"] = "remove"

            resp = requests.patch(
                url=f"{self.url}/permissions",
                headers=self.headers, cookies=cookies, json={"permissions": permissions_data}
            )
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
        data = {"user_name": self.admin_user, "password": self.admin_password}
        resp = requests.post(f"{self.url}/signin", json=data)
        return resp.cookies
