import requests
from requests.cookies import RequestsCookieJar
from typing import TYPE_CHECKING

from cowbird.permissions_synchronizer import Permission, PermissionSynchronizer
from cowbird.services.service import SERVICE_URL_PARAM, Service
from cowbird.utils import CONTENT_TYPE_JSON

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from cowbird.typedefs import SettingsType

MAGPIE_ADMIN_USER = "admin"
MAGPIE_ADMIN_PASSWORD = "qwertyqwerty"


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
        # type: (SettingsType, str, dict) -> None
        """
        Create the magpie instance and instantiate the permission synchronizer that will handle the permission events.

        @param settings: Cowbird settings for convenience
        @param name: Service name
        """
        super(Magpie, self).__init__(settings, name, **kwargs)
        self.permissions_synch = PermissionSynchronizer(self)

        self.headers = {"Content-type": CONTENT_TYPE_JSON}
        self.admin_user = MAGPIE_ADMIN_USER
        self.admin_password = MAGPIE_ADMIN_PASSWORD
        self.auth = (self.admin_user, self.admin_password)

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
        if resp.status_code == 200:
            return resp.json()["resources"]
        else:
            raise RuntimeError("Could not find the input resource's parent resources.")

    def user_created(self, user_name):
        raise NotImplementedError

    def user_deleted(self, user_name):
        raise NotImplementedError

    def permission_created(self, permission):
        self.permissions_synch.create_permission(permission)

    def permission_deleted(self, permission):
        self.permissions_synch.delete_permission(permission)

    def create_permission(self, permissions_data):
        # type: (list[dict]) -> None
        """
        Make sure that the specified permission exists on Magpie.
        """
        cookies = self.login()

        # TODO: check if any permissions_data
        permissions_data[-1]["action"] = "create"

        resp = requests.patch(
            url=f"{self.url}/permissions",
            headers=self.headers, cookies=cookies, json={"permissions": permissions_data}
        )
        # TODO: check resp code
        print(f"post permission response : {resp.status_code}")

    def delete_permission(self, permissions_data):
        # type: (list[dict]) -> None
        """
        Remove the specified permission from Magpie if it exists.
        """
        cookies = self.login()
        # TODO: check if any permissions_data
        permissions_data[-1]["action"] = "remove"

        resp = requests.patch(
            url=f"{self.url}/permissions",
            headers=self.headers, cookies=cookies, json={"permissions": permissions_data}
        )
        # TODO: check resp code
        print(f"post permission response : {resp.status_code}")

    def login(self):
        # type: () -> RequestsCookieJar
        """
        Login to Magpie app using admin credentials.
        """
        data = {"user_name": self.admin_user, "password": self.admin_password,
                "provider_name": "ziggurat"}  # ziggurat = magpie_default_provider
        resp = requests.post("{}/signin".format(self.url), json=data)
        return resp.cookies