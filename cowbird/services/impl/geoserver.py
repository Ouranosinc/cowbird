from celery import chain, shared_task

from cowbird.request_task import RequestTask
from cowbird.services.service import SERVICE_URL_PARAM, SERVICE_WORKSPACE_DIR_PARAM, Service
from cowbird.services.service_factory import ServiceFactory
from cowbird.utils import get_logger

LOGGER = get_logger(__name__)


class Geoserver(Service):
    """
    Keep Geoserver internal representation in sync with the platform.
    """
    required_params = [SERVICE_URL_PARAM, SERVICE_WORKSPACE_DIR_PARAM]

    def __init__(self, name, **kwargs):
        # type: (str, dict) -> None
        """
        Create the geoserver instance.

        @param name: Service name
        """
        super(Geoserver, self).__init__(name, **kwargs)

    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        raise NotImplementedError

    def user_created(self, user_name):
        # ..todo: Replace this simple stub with real implementation
        res = chain(create_workspace.s(user_name),
                    create_datastore.s("default"))
        res.delay()

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

        @param self: Geoserver instance
        @param name: Workspace name
        @return: Workspace id
        """
        LOGGER.info("Creating workspace in geoserver")
        # TODO
        return 1

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
def create_datastore(self, workspace_id, name):
    # type (int, str) -> int
    # Avoid any actual logic in celery task handler, only task related stuff should be done here
    return ServiceFactory().get_service("Geoserver").create_datastore(workspace_id, name)
