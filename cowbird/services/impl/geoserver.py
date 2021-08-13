import os

import requests
from celery import chain, shared_task

from cowbird.request_task import RequestTask
from cowbird.services.service import (Service, SERVICE_URL_PARAM, SERVICE_WORKSPACE_DIR_PARAM, SERVICE_ADMIN_USER,
                                      SERVICE_ADMIN_PASSWORD)
from cowbird.services.service_factory import ServiceFactory
from cowbird.utils import get_logger, CONTENT_TYPE_JSON

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from cowbird.typedefs import SettingsType

LOGGER = get_logger(__name__)


class Geoserver(Service):
    """
    Keep Geoserver internal representation in sync with the platform.
    """
    required_params = [SERVICE_URL_PARAM, SERVICE_WORKSPACE_DIR_PARAM, SERVICE_ADMIN_USER, SERVICE_ADMIN_PASSWORD]

    def __init__(self, settings, name, **kwargs):
        # type: (SettingsType, str, dict) -> None
        """
        Create the geoserver instance.

        @param settings: Cowbird settings for convenience
        @param name: Service name
        """
        super(Geoserver, self).__init__(name, **kwargs)
        self.api_url = "{}/rest".format(self.url)
        self.auth = (self.admin_user, self.admin_password)
        self.headers = {"Content-type": CONTENT_TYPE_JSON}

    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        raise NotImplementedError

    def user_created(self, user_name):
        # res = chain(create_workspace.s(user_name), create_datastore.s(user_name)
        # res.delay()
        self.create_workspace(user_name)
        self.create_datastore(user_name)

    def user_deleted(self, user_name):
        LOGGER.info("Removing workspace in geoserver")
        self.remove_workspace(user_name)

    def permission_created(self, permission):
        raise NotImplementedError

    def permission_deleted(self, permission):
        raise NotImplementedError

    def create_workspace(self, name):
        # type (Geoserver, str) -> int
        """
        Create a new Geoserver workspace.

        @param name: Workspace name
        """
        LOGGER.info("Creating workspace in geoserver")

        request_url = "{}/workspaces/".format(self.api_url)
        payload = {"workspace": {"name": name, "isolated": "True"}}
        request = requests.post(url=request_url, json=payload, auth=self.auth, headers=self.headers)

        request_code = request.status_code
        string_to_find = "Workspace &#39;{}&#39; already exists".format(name)
        if request_code == 201:
            LOGGER.info("Geoserver workspace [%s] was successfully created.", name)
        elif request_code == 401 and string_to_find in request.text:
            # This is done because Geoserver's reply/error code is misleading in this case and
            # returns HTML content.
            LOGGER.error("The following Geoserver workspace already exists: [%s]", name)
        elif request_code == 401:
            LOGGER.error("The request has not been applied because it lacks valid authentication credentials.")
        elif request_code == 500:
            LOGGER.error(request.text)
        else:
            LOGGER.error("There was an error creating the workspace in Geoserver : %s", name)

    def remove_workspace(self, name):
        """
        Removes a workspace from geoserver. Will allso remove all datastores associated with
        the workspace.

        @param name: Workspace name
        """
        request_url = "{}/workspaces/{}?recurse=true".format(self.api_url, name)
        request = requests.delete(url=request_url, auth=self.auth, headers=self.headers)

        request_code = request.status_code
        if request_code == 200:
            LOGGER.info("Geoserver workspace [%s] was successfully removed.", name)
        elif request_code == 403:
            LOGGER.error(
                "Geoserver workspace [%s] is not empty. Make sure `recurse` is set to `true` to delete workspace")
        elif request_code == 404:
            LOGGER.error("Geoserver workspace [%s] was not found.", name)

    def create_datastore(self, workspace_name):
        # type (Geoserver, int, str) -> int
        """
        Create a new Geoserver workspace.

        @param self: Geoserver instance
        @param workspace_name: Workspace id where the datastore must be created
        """
        LOGGER.info("Creating datastore in geoserver")

        datastore_name = "shapefile_datastore_{}".format(workspace_name)
        self._initial_datastore_creation(workspace_name=workspace_name, datastore_name=datastore_name)
        self._configure_datastore_settings(workspace_name=workspace_name, datastore_name=datastore_name)

    #
    # Helper functions
    #
    def _get_datastore_dir(self, workspace_name):
        return os.path.join(self.workspace_dir, workspace_name, "shapefile_datastore")

    @staticmethod
    def _create_datastore_dir(datastore_path):
        try:
            os.mkdir(datastore_path)
        except FileExistsError:
            LOGGER.info("User datastore directory already existing (skip creation): [%s]", datastore_path)

    def _initial_datastore_creation(self, workspace_name, datastore_name):
        """
        Initial creation of the datastore with no connection parameters.

        @param workspace_name: Name of the workspace in which the datastore is created
        @param datastore_name: Name of the datastore that will be created
        """
        request_url = "{}/workspaces/{}/datastores".format(self.api_url, workspace_name)

        payload = {
            "dataStore": {
                "name": datastore_name,
                "type": "Directory of spatial files (shapefiles)",
                "connectionParameters": {
                    "entry": []
                },
            }
        }
        request = requests.post(url=request_url, json=payload, auth=self.auth, headers=self.headers)

        request_code = request.status_code
        if request_code == 201:
            LOGGER.info("Datastore [%s] has been successfully created.", datastore_name)
        elif request_code == 401:
            LOGGER.error("The request has not been applied because it lacks valid authentication credentials.")
        elif request_code == 500:
            LOGGER.error(request.text)
        else:
            LOGGER.error("There was an error creating the following datastore: [%s]", datastore_name)

    def _configure_datastore_settings(self, datastore_name, workspace_name):
        """
        Configures the connection parameters of the datastore.

        This is done as a secondary step because Geoserver tends to create the wrong type of datastore
        (shapefile instead of directory of shapefiles) when setting them at creation.

        @param workspace_name: Name of the workspace in which the datastore is created
        @param datastore_name: Name of the datastore that will be created
        @return:
        """
        datastore_path = self._get_datastore_dir(workspace_name)
        self._create_datastore_dir(datastore_path)
        geoserver_datastore_path = "file://{}".format(datastore_path)

        request_url = "{}/workspaces/{}/datastores/{}".format(self.api_url, workspace_name, datastore_name)
        payload = {
            "dataStore": {
                "name": datastore_name,
                "type": "Directory of spatial files (shapefiles)",
                "connectionParameters": {
                    "entry": [
                        {'$': 'UTF-8',
                         '@key': 'charset'},
                        {'$': 'shapefile',
                         '@key': 'filetype'},
                        {'$': 'true',
                         '@key': 'create spatial '
                                 'index'},
                        {'$': 'true',
                         '@key': 'memory mapped '
                                 'buffer'},
                        {'$': 'GMT',
                         '@key': 'timezone'},
                        {'$': 'true',
                         '@key': 'enable spatial '
                                 'index'},
                        {'$': 'http://{}'.format(datastore_name),
                         '@key': 'namespace'},
                        {'$': 'true',
                         '@key': 'cache and reuse '
                                 'memory maps'},
                        {'$': geoserver_datastore_path,
                         '@key': 'url'},
                        {'$': 'shape',
                         '@key': 'fstype'},
                    ]
                },
            }
        }
        request = requests.put(url=request_url, json=payload, auth=self.auth, headers=self.headers)

        request_code = request.status_code
        if request_code == 200:
            LOGGER.info("Datastore [%s] has been successfully configured.", datastore_name)
        elif request_code == 401:
            LOGGER.error("The request has not been applied because it lacks valid authentication credentials.")
        elif request_code == 500:
            LOGGER.error(request.text)
        else:
            LOGGER.error("There was an error configuring the following datastore: [%s]", datastore_name)


@shared_task(bind=True, base=RequestTask)
def create_workspace(self, name):
    # type (str) -> int
    # Avoid any actual logic in celery task handler, only task related stuff should be done here
    return ServiceFactory().get_service("Geoserver").create_workspace(name)


@shared_task(bind=True, base=RequestTask)
def create_datastore(self, workspace_name):
    # type (int, str) -> int
    # Avoid any actual logic in celery task handler, only task related stuff should be done here
    return ServiceFactory().get_service("Geoserver").create_datastore(workspace_name)
