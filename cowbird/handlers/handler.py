import abc
import math
import os
from typing import Any, List
from typing_extensions import Literal

from cowbird.permissions_synchronizer import Permission
from cowbird.typedefs import JSON, SettingsType
from cowbird.utils import get_logger, get_ssl_verify, get_timeout

AnyHandlerParameter = Literal["priority", "url", "workspace_dir"]

HANDLER_PRIORITY_PARAM: AnyHandlerParameter = "priority"
HANDLER_URL_PARAM: AnyHandlerParameter = "url"
HANDLER_WORKSPACE_DIR_PARAM: AnyHandlerParameter = "workspace_dir"

HANDLER_PARAMETERS = frozenset([
    HANDLER_PRIORITY_PARAM,
    HANDLER_URL_PARAM,
    HANDLER_WORKSPACE_DIR_PARAM
])

LOGGER = get_logger(__name__)


class HandlerConfigurationException(Exception):
    """
    Exception thrown when a handler cannot be instantiated because of a bad configuration.
    """


class Handler(abc.ABC):
    __slots__ = ["settings",
                 "name",
                 "ssl_verify",
                 "timeout",
                 HANDLER_PRIORITY_PARAM,
                 HANDLER_URL_PARAM,
                 HANDLER_WORKSPACE_DIR_PARAM
                 ]
    """
    Handler interface used to notify implemented handlers of users/permissions changes.

    .. todo:: At some point we will need a consistency function that goes through all Magpie users and make sure that
              handlers are up-to-date.
    """

    @property
    @abc.abstractmethod
    def required_params(self) -> List[AnyHandlerParameter]:
        raise NotImplementedError

    def __init__(self, settings: SettingsType, name: str, **kwargs: Any) -> None:
        """
        :param settings: Cowbird settings for convenience
        :param name: Handler name
        :param kwargs: The base class handle, but doesn't require the following variables:

        :param url: Location of the web service represented by the cowbird handler
        :param workspace_dir: Workspace directory
        :param priority: Relative priority between handlers while handling events.
                         Lower value has higher priority, default value is last.
        """
        if getattr(self, "required_params", None) is None:
            raise NotImplementedError("Handler 'required_params' must be overridden in inheriting class.")
        self.settings = settings
        self.name = name
        self.priority = kwargs.get(HANDLER_PRIORITY_PARAM, math.inf)
        self.url = kwargs.get(HANDLER_URL_PARAM, None)
        self.workspace_dir = kwargs.get(HANDLER_WORKSPACE_DIR_PARAM, None)
        # Handlers making outbound requests should use these settings to avoid SSLError on test/dev setup
        self.ssl_verify = get_ssl_verify(self.settings)
        self.timeout = get_timeout(self.settings)
        for required_param in self.required_params:  # pylint: disable=E1101,no-member
            if required_param not in HANDLER_PARAMETERS:
                raise HandlerConfigurationException(f"Invalid handler parameter : {required_param}")
            if getattr(self, required_param) is None:
                error_msg = f"{self.__class__.__name__} handler requires the following missing configuration " \
                            f"parameter : [{required_param}]"
                LOGGER.error(error_msg)
                raise HandlerConfigurationException(error_msg)

    def json(self) -> JSON:
        return {"name": self.name}

    def _user_workspace_dir(self, user_name: str) -> str:
        return os.path.join(self.workspace_dir, user_name)

    @abc.abstractmethod
    def get_resource_id(self, resource_full_name: str) -> int:
        """
        Each handler must provide this implementation required by the permission synchronizer.

        The function needs to find the resource id in Magpie from the resource full name using its knowledge of the
        service. If the resource doesn't already exist, the function needs to create it, again using its knowledge of
        resource type and parent resource type if required.

        .. todo: Could be moved to another abstract class (SynchronizableHandler) that some Handler could implement
                 Permissions_synchronizer would then check instance type of handler while loading sync config

                 TODO: Check if this TODO is still relevant considering latest Magpie implementation?
        """
        raise NotImplementedError

    @abc.abstractmethod
    def user_created(self, user_name: str) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def user_deleted(self, user_name: str) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def permission_created(self, permission: Permission) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def permission_deleted(self, permission: Permission) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def resync(self):
        raise NotImplementedError
