#!/usr/bin/env python
"""
Additional typing definitions.
"""

from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Literal,
    MutableMapping,
    MutableSequence,
    Optional,
    Tuple,
    Type,
    TypedDict,
    Union
)
from typing_extensions import TypeAlias

from celery.app import Celery
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPException
from pyramid.registry import Registry
from pyramid.request import Request
from pyramid.response import Response as PyramidResponse
from requests.cookies import RequestsCookieJar
from requests.models import Response as RequestsResponse
from requests.structures import CaseInsensitiveDict
from webob.headers import EnvironHeaders, ResponseHeaders
from webob.response import Response as WebobResponse

if TYPE_CHECKING:
    from magpie.typedefs import PermissionConfigItem
    from webtest.response import TestResponse  # only with install-dev

    from cowbird.database.stores import StoreInterface

StoreInterfaceType: TypeAlias = "StoreInterface"
PermissionConfigItemType: TypeAlias = "PermissionConfigItem"
TestResponseType: TypeAlias = "TestResponse"

Number = Union[int, float]
SettingValue = Union[str, Number, bool, None]
SettingsType = Dict[str, SettingValue]
AnySettingsContainer = Union[Configurator, Registry, Request, SettingsType]
AnyRegistryContainer = Union[Configurator, Registry, Request, Celery]

ParamsType = Dict[str, Any]
CookiesType = Union[Dict[str, str], List[Tuple[str, str]]]
HeadersType = Union[Dict[str, str], List[Tuple[str, str]]]
AnyHeadersType = Union[HeadersType, ResponseHeaders, EnvironHeaders, CaseInsensitiveDict]
AnyCookiesType = Union[CookiesType, RequestsCookieJar]
AnyResponseType = Union[WebobResponse, PyramidResponse, RequestsResponse, HTTPException, TestResponseType]

# pylint: disable=C0103,invalid-name
ValueType = Union[str, Number, bool]
AnyValueType = Optional[ValueType]  # avoid naming ambiguity with PyWPS AnyValue
AnyKey = Union[str, int]
# add more levels of explicit definitions than necessary to simulate JSON recursive structure better than 'Any'
# amount of repeated equivalent definition makes typing analysis 'work well enough' for most use cases
_JSON: TypeAlias = "JSON"
_JsonObjectItemAlias: TypeAlias = "_JsonObjectItem"
_JsonListItemAlias: TypeAlias = "_JsonListItem"
_JsonObjectItem = MutableMapping[str, Union[_JSON, _JsonObjectItemAlias, _JsonListItemAlias, AnyValueType]]
_JsonListItem = MutableSequence[Union[_JsonObjectItem, _JsonListItemAlias, AnyValueType]]
_JsonItem = Union[_JsonObjectItem, _JsonListItem, AnyValueType]
# NOTE:
#   Although 'JSON' should allow referring directly to anything between 'Dict[str, JSON]', 'List[JSON]'
#   or 'AnyValueType', this can a lot of false positives typing detections. Sometimes, it is better to provide
#   the explicitly type expected (e.g.: 'List[JSON]') when necessary to disambiguate some situations.
JSON = Union[MutableMapping[str, _JsonItem], MutableSequence[_JsonItem], AnyValueType]

HTTPMethod = Literal[
    "HEAD",
    "GET",
    "PUT",
    "POST",
    "PATCH",
    "DELETE",
    # others available, but not common for API definition
]

# registered configurations
ConfigItem = Dict[str, JSON]
ConfigList = List[ConfigItem]
ConfigDict = Dict[str, Union[str, ConfigItem, ConfigList, JSON]]
ConfigResTokenInfo = TypedDict("ConfigResTokenInfo", {"has_multi_token": bool, "named_tokens": set})
ConfigSegment = TypedDict("ConfigSegment", {"name": str, "type": str})

ResourceSegment = TypedDict("ResourceSegment", {"resource_name": str, "resource_type": str})
ResourceTree = List[Dict[str, ResourceSegment]]
PermissionResourceData = Union[PermissionConfigItemType, ResourceSegment]
PermissionDataEntry = TypedDict(
    "PermissionDataEntry",
    {
        "res_path": List[PermissionResourceData],
        "permissions": Dict[str, List[str]],
    },
    total=True,
)
PermissionData = Dict[str, PermissionDataEntry]

StoreSelector = Union[Type[StoreInterfaceType], StoreInterfaceType, str]
