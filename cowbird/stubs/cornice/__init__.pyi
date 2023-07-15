from typing import Any, Callable, Dict, List, Optional, Protocol, TypeVar
from typing_extensions import ParamSpec

from colander import SchemaNode
from pyramid.request import Request

from cowbird.typedefs import JSON, AnyResponseType

ViewCallableParam = ParamSpec("ViewCallableParam")
ViewCallableType = TypeVar("ViewCallableType", bound=Callable[[Request], AnyResponseType])

ViewCallableDecorator = Callable[[Request], AnyResponseType]
ViewCallableService = Callable[[ViewCallableDecorator], ViewCallableDecorator]

# class ViewService(Protocol):
#     def __call__(
#         self,
#         view: Callable[ViewCallableParam, ViewCallableType],
#     ) -> Callable[ViewCallableParam, ViewCallableType]: ...


class Service:
    @property
    def name(self) -> str: ...

    @property
    def path(self) -> str: ...

    @staticmethod
    def head(
        *,
        schema: SchemaNode,
        response_schemas: Dict[str, SchemaNode],
        tags: Optional[List[str]] = None,
        api_security: Optional[JSON] = None,
    ) -> ViewCallableService: ...

    @staticmethod
    def get(
        *,
        schema: SchemaNode,
        response_schemas: Dict[str, SchemaNode],
        tags: Optional[List[str]] = None,
        api_security: Optional[JSON] = None,
    ) -> ViewCallableService: ...

    @staticmethod
    def put(
        *,
        schema: SchemaNode,
        response_schemas: Dict[str, SchemaNode],
        tags: Optional[List[str]] = None,
        api_security: Optional[JSON] = None,
    ) -> ViewCallableService: ...

    @staticmethod
    def post(
        *,
        schema: SchemaNode,
        response_schemas: Dict[str, SchemaNode],
        tags: Optional[List[str]] = None,
        api_security: Optional[JSON] = None,
    ) -> ViewCallableService: ...

    @staticmethod
    def patch(
        *,
        schema: SchemaNode,
        response_schemas: Dict[str, SchemaNode],
        tags: Optional[List[str]] = None,
        api_security: Optional[JSON] = None,
    ) -> ViewCallableService: ...

    @staticmethod
    def delete(
        *,
        schema: SchemaNode,
        response_schemas: Dict[str, SchemaNode],
        tags: Optional[List[str]] = None,
        api_security: Optional[JSON] = None,
    ) -> ViewCallableService: ...
