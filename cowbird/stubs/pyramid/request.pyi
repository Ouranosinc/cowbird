from typing import Optional

from pyramid.registry import Registry

from cowbird.typedefs import JSON, HTTPMethod


class Request:
    accept: Optional[str]
    method: HTTPMethod
    upath_info: str
    url: str
    json_body: JSON

    @property
    def registry(self) -> Registry: ...
