from typing import Callable, Optional, Protocol

from pyramid.request import Request

from cowbird.typedefs import AnyResponseType, HTTPMethod

# class ViewCallable(Protocol):
#     def __call__(self, request: Request) -> AnyResponseType: ...

ViewCallable = Callable[[Request], AnyResponseType]

#def view_config(*, route_name: str, request_method: HTTPMethod, permission: Optional[str] = None) -> ViewCallable: ...

class view_config:  # noqa  # exact name required to match actual definition from pyramid
    def __init__(self, *, route_name: str, request_method: HTTPMethod, permission: Optional[str] = None) -> None: ...

    def __call__(self, view: ViewCallable) -> ViewCallable: ...
