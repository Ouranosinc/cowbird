import os
import abc
import math
from cowbird.utils import get_logger

SERVICE_PRIORITY_PARAM = "priority"
SERVICE_URL_PARAM = "url"
SERVICE_WORKSPACE_DIR_PARAM = "workspace_dir"

SERVICE_PARAMETERS = frozenset([
    SERVICE_PRIORITY_PARAM,
    SERVICE_URL_PARAM,
    SERVICE_WORKSPACE_DIR_PARAM,
])

LOGGER = get_logger(__name__)


class ServiceConfigurationException(Exception):
    """
    Exception thrown when a service cannot be instantiated because of a bad configuration
    """


class Service(abc.ABC):
    __slots__ = ["required_params"]

    """
    Service interface used to notify implemented services of users/permissions changes.

    .. todo:: At some point we will need a consistency function that goes through all Magpie users and make sure that
              services are up to date.
    """

    def __init__(self, name, **kwargs):
        # type (str, dict) -> None
        """
        @param name: Service name
        @param kwargs: The base class handle, but doesn't require the following variables:
                        param `priority`: Relative priority between services while handling events
                                          (lower value has higher priority, default value is last)
                        param `url`: Location of the web service represented by the cowbird service
                        param `workspace_dir`:
        """
        if self.required_params is None:  # pylint: disable=E1101,no-member
            raise NotImplementedError("Service 'required_params' must be overridden in inheriting class.")
        self.name = name
        self.priority = kwargs.get(SERVICE_PRIORITY_PARAM, math.inf)
        self.url = kwargs.get(SERVICE_URL_PARAM, None)
        self.workspace_dir = kwargs.get(SERVICE_WORKSPACE_DIR_PARAM, None)
        for required_param in self.required_params:
            if required_param not in SERVICE_PARAMETERS:
                raise Exception("Invalid service parameter : {}".format(required_param))
            if getattr(self, required_param) is None:
                error_msg = "{} service requires the following missing configuration parameter : [{}]".format(
                    self.__class__.__name__,
                    required_param
                )
                LOGGER.error(error_msg)
                raise ServiceConfigurationException(error_msg)

    def json(self):
        return {"name": self.name}

    def _user_workspace_dir(self, user_name):
        return os.path.join(self.workspace_dir, user_name)

    @abc.abstractmethod
    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        """
        Each service must provide this implementation required by the permission synchronizer.

        The function needs to find the resource id in Magpie from the resource full name using its knowledge of the
        service. If the resource doesn't already exist, the function needs to create it, again using its knowledge of
        resource type and parent resource type if required.

        .. todo: Could be moved to another abstract class (SynchronizableService) that some Service could implement
                 Permissions_synchronizer would then check instance type of service while loading sync config
        """
        raise NotImplementedError

    @abc.abstractmethod
    def user_created(self, user_name):
        raise NotImplementedError

    @abc.abstractmethod
    def user_deleted(self, user_name):
        raise NotImplementedError

    @abc.abstractmethod
    def permission_created(self, permission):
        raise NotImplementedError

    @abc.abstractmethod
    def permission_deleted(self, permission):
        raise NotImplementedError
