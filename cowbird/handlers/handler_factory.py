import importlib
from typing import TYPE_CHECKING, Dict, List, Literal, MutableMapping, Optional, overload

from cowbird.config import get_all_configs
from cowbird.typedefs import HandlerConfig
from cowbird.utils import SingletonMeta, get_config_path, get_logger, get_settings

if TYPE_CHECKING:
    from cowbird.handlers.handler import Handler
    from cowbird.handlers.impl.catalog import Catalog as CatalogHandler
    from cowbird.handlers.impl.filesystem import FileSystem as FileSystemHandler
    from cowbird.handlers.impl.geoserver import Geoserver as GeoserverHandler
    from cowbird.handlers.impl.magpie import Magpie as MagpieHandler
    from cowbird.handlers.impl.nginx import Nginx as NginxHandler
    from cowbird.handlers.impl.thredds import Thredds as ThreddsHandler

LOGGER = get_logger(__name__)

VALID_HANDLERS = ["Catalog", "Geoserver", "Magpie", "Nginx", "Thredds", "FileSystem"]


class HandlerFactory(metaclass=SingletonMeta):
    """
    Create handler instance using handler name.
    """

    def __init__(self) -> None:
        self.settings = get_settings(None, app=True)
        config_path = get_config_path()
        handlers_configs = get_all_configs(config_path, "handlers", allow_missing=True)
        self.handlers_cfg: Dict[str, HandlerConfig] = {}
        for handlers_config in handlers_configs:
            if not handlers_config:
                LOGGER.warning("Handlers configuration is empty.")
                continue
            for name, cfg in handlers_config.items():
                if name in self.handlers_cfg:
                    LOGGER.warning("Ignoring a duplicate handler configuration for [%s].", name)
                else:
                    self.handlers_cfg[name] = cfg
        self.handlers: MutableMapping[str, "Handler"] = {}
        LOGGER.info("Handlers config : [%s]", ", ".join([f"{name} [{cfg.get('active', False)}]"
                                                         for name, cfg in self.handlers_cfg.items()]))

    @overload
    def create_handler(self, name: Literal["Catalog"]) -> "CatalogHandler":
        ...

    @overload
    def create_handler(self, name: Literal["FileSystem"]) -> "FileSystemHandler":
        ...

    @overload
    def create_handler(self, name: Literal["Geoserver"]) -> "GeoserverHandler":
        ...

    @overload
    def create_handler(self, name: Literal["Magpie"]) -> "MagpieHandler":
        ...

    @overload
    def create_handler(self, name: Literal["Nginx"]) -> "NginxHandler":
        ...

    @overload
    def create_handler(self, name: Literal["Thredds"]) -> "ThreddsHandler":
        ...

    @overload
    def create_handler(self, name: str) -> Optional["Handler"]:
        ...

    def create_handler(self, name: str) -> Optional["Handler"]:
        """
        Instantiates a new `Handler` implementation using its name, overwriting an existing instance if required.
        """
        handler = None
        if (
            name in VALID_HANDLERS and
            name in self.handlers_cfg and
            self.handlers_cfg[name].get("active", False)
        ):
            module = importlib.import_module(".".join(["cowbird.handlers.impl", name.lower()]))
            cls = getattr(module, name)
            handler = cls(settings=self.settings, name=name, **self.handlers_cfg[name])
        self.handlers[name] = handler
        return handler

    @overload
    def get_handler(self, name: Literal["Catalog"]) -> "CatalogHandler":
        ...

    @overload
    def get_handler(self, name: Literal["FileSystem"]) -> "FileSystemHandler":
        ...

    @overload
    def get_handler(self, name: Literal["Geoserver"]) -> "GeoserverHandler":
        ...

    @overload
    def get_handler(self, name: Literal["Magpie"]) -> "MagpieHandler":
        ...

    @overload
    def get_handler(self, name: Literal["Nginx"]) -> "NginxHandler":
        ...

    @overload
    def get_handler(self, name: Literal["Thredds"]) -> "ThreddsHandler":
        ...

    @overload
    def get_handler(self, name: str) -> Optional["Handler"]:
        ...

    def get_handler(self, name: str) -> Optional["Handler"]:
        """
        Instantiates a `Handler` implementation using its name if it doesn't exist or else returns the existing one from
        cache.
        """
        try:
            return self.handlers[name]
        except KeyError:
            return self.create_handler(name)

    def get_active_handlers(self) -> List["Handler"]:
        """
        Return a sorted list by priority of `Handler` implementation activated in the config.
        """
        return sorted(filter(None, [self.get_handler(name) for name in self.handlers_cfg]),
                      key=lambda handler: handler.priority)
