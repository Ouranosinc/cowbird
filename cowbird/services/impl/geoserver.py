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
        res = chain(create_workspace.si(user_name) | create_datastore.si(user_name))
        res.delay()

    def user_deleted(self, user_name):
        LOGGER.info("Removing workspace in geoserver")
        remove_workspace.delay(user_name)

    def permission_created(self, permission):
        raise NotImplementedError

    def permission_deleted(self, permission):
        raise NotImplementedError

    def create_workspace(self, name):
        # type (Geoserver, str) -> None
        """
        Create a new Geoserver workspace.

        @param name: Workspace name
        """
        LOGGER.info("Creating workspace in geoserver")

        response = self._create_workspace_request(name)
        response_code = response.status_code
        string_to_find = "Workspace &#39;{}&#39; already exists".format(name)
        if response_code == 201:
            LOGGER.info("Geoserver workspace [%s] was successfully created.", name)
        elif response_code == 401 and string_to_find in response.text:
            # This is done because Geoserver's reply/error code is misleading in this case and
            # returns HTML content.
            LOGGER.error("The following Geoserver workspace already exists: [%s]", name)
        elif response_code == 401:
            LOGGER.error("The request has not been applied because it lacks valid authentication credentials.")
        elif response_code == 500:
            LOGGER.error(response.text)
        else:
            LOGGER.error("There was an error creating the workspace in Geoserver : %s", name)

    def remove_workspace(self, name):
        # type (Geoserver, str) -> None
        """
        Removes a workspace from geoserver. Will also remove all datastores associated with
        the workspace.

        @param name: Workspace name
        """
        response = self._remove_workspace_request(name)
        response_code = response.status_code
        if response_code == 200:
            LOGGER.info("Geoserver workspace [%s] was successfully removed.", name)
        elif response_code == 403:
            LOGGER.error(
                "Geoserver workspace [%s] is not empty. Make sure `recurse` is set to `true` to delete workspace")
        elif response_code == 404:
            LOGGER.error("Geoserver workspace [%s] was not found.", name)

    def create_datastore(self, workspace_name):
        # type (Geoserver, str) -> None
        """
        Create a new Geoserver workspace.

        @param self: Geoserver instance
        @param workspace_name: Workspace id where the datastore must be created
        """
        LOGGER.info("Creating datastore in geoserver")

        datastore_name = self.get_datastore_name(workspace_name)
        creation_response = self._create_datastore_request(workspace_name=workspace_name, datastore_name=datastore_name)
        response_code = creation_response.status_code
        if response_code == 201:
            LOGGER.info("Datastore [%s] has been successfully created.", datastore_name)
        elif response_code == 401:
            LOGGER.error("The request has not been applied because it lacks valid authentication credentials.")
        elif response_code == 500:
            LOGGER.error(creation_response.text)
        else:
            LOGGER.error("There was an error creating the following datastore: [%s]", datastore_name)

        datastore_path = self._get_datastore_dir(workspace_name)
        self._create_datastore_dir(datastore_path)

        configuration_response = self._configure_datastore_request(workspace_name=workspace_name,
                                                                   datastore_name=datastore_name,
                                                                   datastore_path=datastore_path)
        response_code = configuration_response.status_code
        if response_code == 200:
            LOGGER.info("Datastore [%s] has been successfully configured.", datastore_name)
        elif response_code == 401:
            LOGGER.error("The request has not been applied because it lacks valid authentication credentials.")
        elif response_code == 500:
            LOGGER.error(configuration_response.text)
        else:
            LOGGER.error("There was an error configuring the following datastore: [%s]", datastore_name)

    @staticmethod
    def get_datastore_name(workspace_name):
        return "shapefile_datastore_{}".format(workspace_name)

    def publish_shapefile(self, workspace_name, filename):
        datastore_name = self.get_datastore_name(workspace_name)
        response = self._publish_shapefile_request(workspace_name=workspace_name,
                                                   datastore_name=datastore_name,
                                                   filename=filename)
        response_code = response.status_code
        if response_code == 201:
            LOGGER.info("Shapefile [%s] has been successfully publish by Geoserver.", filename)
        elif response_code == 401:
            LOGGER.error("The request has not been applied because it lacks valid authentication credentials.")
        elif response_code == 500:
            LOGGER.error(response.text)
        else:
            LOGGER.error("There was an error publishing the following shapefile: [%s]", filename)

    def remove_shapefile(self, workspace_name, filename):
        datastore_name = self.get_datastore_name(workspace_name)
        response = self._remove_shapefile_request(workspace_name=workspace_name,
                                                  datastore_name=datastore_name,
                                                  filename=filename)
        response_code = response.status_code
        if response_code == 200:
            LOGGER.info("Shapefile [%s] has been successfully publish by Geoserver.", filename)
        elif response_code == 401:
            LOGGER.error("The request has not been applied because it lacks valid authentication credentials.")
        elif response_code == 500:
            LOGGER.error(response.text)
        else:
            LOGGER.error("There was an error publishing the following shapefile: [%s]", filename)

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
    def _create_workspace_request(self, workspace_name):
        # type (Geoserver, str) -> Response
        request_url = "{}/workspaces/".format(self.api_url)
        payload = {"workspace": {"name": workspace_name, "isolated": "True"}}
        request = requests.post(url=request_url, json=payload, auth=self.auth, headers=self.headers)
        return request

    def _remove_workspace_request(self, workspace_name):
        request_url = "{}/workspaces/{}?recurse=true".format(self.api_url, workspace_name)
        request = requests.delete(url=request_url, auth=self.auth, headers=self.headers)
        return request

    def _get_datastore_dir(self, workspace_name):
        # type (Geoserver, str) -> str
        return os.path.join(self.workspace_dir, workspace_name, "shapefile_datastore")

    @staticmethod
    def _create_datastore_dir(datastore_path):
        # type (str) -> None
        try:
            os.mkdir(datastore_path)
        except FileExistsError:
            LOGGER.info("User datastore directory already existing (skip creation): [%s]", datastore_path)

    def _create_datastore_request(self, workspace_name, datastore_name):
        # type (Geoserver, str, str) -> None
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
        return request

    def _configure_datastore_request(self, workspace_name, datastore_name, datastore_path):
        # type (Geoserver, str, str) -> None
        """
        Configures the connection parameters of the datastore.

        This is done as a secondary step because Geoserver tends to create the wrong type of datastore
        (shapefile instead of directory of shapefiles) when setting them at creation.

        @param workspace_name: Name of the workspace in which the datastore is created
        @param datastore_name: Name of the datastore that will be created
        @return:
        """
        geoserver_datastore_path = "file://{}".format(datastore_path)
        request_url = "{}/workspaces/{}/datastores/{}".format(self.api_url, workspace_name, datastore_name)
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
                         "@key": "create spatial "
                                 "index"},
                        {"$": "true",
                         "@key": "memory mapped "
                                 "buffer"},
                        {"$": "GMT",
                         "@key": "timezone"},
                        {"$": "true",
                         "@key": "enable spatial "
                                 "index"},
                        {"$": "http://{}".format(datastore_name),
                         "@key": "namespace"},
                        {"$": "true",
                         "@key": "cache and reuse "
                                 "memory maps"},
                        {"$": geoserver_datastore_path,
                         "@key": "url"},
                        {"$": "shape",
                         "@key": "fstype"},
                    ]
                },
            }
        }
        request = requests.put(url=request_url, json=payload, auth=self.auth, headers=self.headers)
        return request

    def _publish_shapefile_request(self, workspace_name, datastore_name, filename):
        request_url = "{}/workspaces/{}/datastores/{}/featuretypes".format(self.api_url,
                                                                           workspace_name,
                                                                           datastore_name)

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
        request = requests.post(url=request_url, json=payload, auth=self.auth, headers=self.headers)
        return request

    def _remove_shapefile_request(self, workspace_name, datastore_name, filename):
        request_url = "{}/workspaces/{}/datastores/{}/featuretypes/{}?recurse=true".format(self.api_url,
                                                                                           workspace_name,
                                                                                           datastore_name,
                                                                                           filename)
        request = requests.delete(url=request_url, auth=self.auth, headers=self.headers)
        return request


@shared_task(bind=True, base=RequestTask)
def create_workspace(self, name):
    # type (str) -> None
    # Avoid any actual logic in celery task handler, only task related stuff should be done here
    return ServiceFactory().get_service("Geoserver").create_workspace(name)


@shared_task(bind=True, base=RequestTask)
def create_datastore(self, name):
    # type (str) -> None
    # Avoid any actual logic in celery task handler, only task related stuff should be done here
    return ServiceFactory().get_service("Geoserver").create_datastore(name)


@shared_task(bind=True, base=RequestTask)
def remove_workspace(self, name):
    # type (str) -> None
    # Avoid any actual logic in celery task handler, only task related stuff should be done here
    return ServiceFactory().get_service("Geoserver").remove_workspace(name)
