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
    def __init__(
        self,
        name: str,
        path: Optional[str] = None,
        description: Optional[str] = None,
        cors_policy: Dict[str, str] = None,
        pyramid_route: Optional[str] = None,
        depth: int = 1,
        **kwargs: Any,
    ) -> None: ...

    @property
    def name(self) -> str: ...

    @property
    def path(self) -> str: ...

    @staticmethod
    def head(
        *,
        response_schemas: Dict[str, SchemaNode],
        schema: Optional[SchemaNode] = None,
        tags: Optional[List[str]] = None,
        api_security: Optional[JSON] = None,
    ) -> ViewCallableService: ...

    @staticmethod
    def get(
        *,
        response_schemas: Dict[str, SchemaNode],
        schema: Optional[SchemaNode] = None,
        tags: Optional[List[str]] = None,
        api_security: Optional[JSON] = None,
    ) -> ViewCallableService: ...

    @staticmethod
    def put(
        *,
        response_schemas: Dict[str, SchemaNode],
        schema: Optional[SchemaNode] = None,
        tags: Optional[List[str]] = None,
        api_security: Optional[JSON] = None,
    ) -> ViewCallableService: ...

    @staticmethod
    def post(
        *,
        response_schemas: Dict[str, SchemaNode],
        schema: Optional[SchemaNode] = None,
        tags: Optional[List[str]] = None,
        api_security: Optional[JSON] = None,
    ) -> ViewCallableService: ...

    @staticmethod
    def patch(
        *,
        response_schemas: Dict[str, SchemaNode],
        schema: Optional[SchemaNode] = None,
        tags: Optional[List[str]] = None,
        api_security: Optional[JSON] = None,
    ) -> ViewCallableService: ...

    @staticmethod
    def delete(
        *,
        response_schemas: Dict[str, SchemaNode],
        schema: Optional[SchemaNode] = None,
        tags: Optional[List[str]] = None,
        api_security: Optional[JSON] = None,
    ) -> ViewCallableService: ...
