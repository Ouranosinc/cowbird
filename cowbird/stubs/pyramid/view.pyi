from typing import Optional, Protocol

from pyramid.request import Request

from cowbird.typedefs import AnyResponseType, HTTPMethod


class ViewCallable(Protocol):
    def __call__(self, request: Request) -> AnyResponseType: ...


def view_config(*, route_name: str, request_method: HTTPMethod, permission: Optional[str] = None) -> ViewCallable: ...
