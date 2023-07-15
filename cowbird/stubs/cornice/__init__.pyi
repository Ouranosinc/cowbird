from typing import Dict, List, Protocol

from colander import SchemaNode
from pyramid.request import Request

from cowbird.typedefs import JSON, AnyResponseType

class ViewCallable(Protocol):
    def __call__(self, request: Request) -> AnyResponseType: ...


class Service:
    @property
    def name(self) -> str: ...
    @property
    def path(self) -> str: ...
    def head(
        self,
        *,
        schema: SchemaNode,
        response_schemas: Dict[str, SchemaNode],
        tags: List[str],
        api_security: JSON,
    ) -> ViewCallable: ...
    def get(
        self,
        *,
        schema: SchemaNode,
        response_schemas: Dict[str, SchemaNode],
        tags: List[str],
        api_security: JSON,
    ) -> ViewCallable: ...
    def put(
        self,
        *,
        schema: SchemaNode,
        response_schemas: Dict[str, SchemaNode],
        tags: List[str],
        api_security: JSON,
    ) -> ViewCallable: ...
    def post(
        self,
        *,
        schema: SchemaNode,
        response_schemas: Dict[str, SchemaNode],
        tags: List[str],
        api_security: JSON,
    ) -> ViewCallable: ...
    def patch(
        self,
        *,
        schema: SchemaNode,
        response_schemas: Dict[str, SchemaNode],
        tags: List[str],
        api_security: JSON,
    ) -> ViewCallable: ...
    def delete(
        self,
        *,
        schema: SchemaNode,
        response_schemas: Dict[str, SchemaNode],
        tags: List[str],
        api_security: JSON,
    ) -> ViewCallable: ...
