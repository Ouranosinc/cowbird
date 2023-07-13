import abc

from cowbird.database.stores import StoreInterface
from cowbird.typedefs import JSON, AnySettingsContainer, StoreSelector


class DatabaseInterface(metaclass=abc.ABCMeta):
    """
    Return the unique identifier of db type matching settings.
    """
    __slots__ = ["type"]

    def __init__(self, _: AnySettingsContainer) -> None:
        """
        Database interface defining a minimum set of function mostly around store management.
        """
        if not self.type:  # pylint: disable=E1101,no-member
            raise NotImplementedError("Database 'type' must be overridden in inheriting class.")

    @staticmethod
    def _get_store_type(store_type: StoreSelector) -> str:
        if isinstance(store_type, StoreInterface):
            return store_type.type
        if isinstance(store_type, type) and issubclass(store_type, StoreInterface):
            return store_type.type
        if isinstance(store_type, str):
            return store_type
        raise TypeError(f"Unsupported store type selector: [{store_type}] ({type(store_type)})")

    @abc.abstractmethod
    def get_store(self, store_type, *store_args, **store_kwargs):
        raise NotImplementedError

    @abc.abstractmethod
    def reset_store(self, store_type: StoreSelector) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get_session(self):
        raise NotImplementedError

    @abc.abstractmethod
    def get_information(self) -> JSON:
        """
        :returns: {'version': version, 'type': db_type}
        """
        raise NotImplementedError

    @abc.abstractmethod
    def is_ready(self) -> bool:
        raise NotImplementedError
