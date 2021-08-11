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

    def user_deleted(self, user_name):
        raise NotImplementedError

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

        request = requests.post(
            url=request_url,
            json=payload,
            auth=self.auth,
            headers=self.headers,
        )

        request_code = request.status_code
        if request_code == 201:
            LOGGER.info("Geoserver workspace was successfully created")
        elif request_code == 409:
            LOGGER.error("Unable to create Geoserver workspace as it already exists")
        else:
            LOGGER.error("There was an error creating the workspace in Geoserver")

    def create_datastore(self, workspace_id, name):
        # type (Geoserver, int, str) -> int
        """
        Create a new Geoserver workspace.

        @param self: Geoserver instance
        @param workspace_id: Workspace id where the datastore must be created
        @param name: Datastore name
        @return: Datastore id
        """
        LOGGER.info("Creating datastore in geoserver")
        # TODO
        return 1


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
