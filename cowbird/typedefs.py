#!/usr/bin/env python
"""
Additional typing definitions.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Type, TypedDict, Union
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
from webtest.response import TestResponse

if TYPE_CHECKING:
    from magpie.typedefs import PermissionConfigItem

    from cowbird.database.stores import StoreInterface
StoreInterfaceType: TypeAlias = "StoreInterface"
PermissionConfigItemType: TypeAlias = "PermissionConfigItem"

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
AnyResponseType = Union[WebobResponse, PyramidResponse, RequestsResponse, HTTPException, TestResponse]

# pylint: disable=C0103,invalid-name
ValueType = Union[str, Number, bool]
AnyValueType = Optional[ValueType]  # avoid naming ambiguity with PyWPS AnyValue
AnyKey = Union[str, int]
# add more levels of explicit definitions than necessary to simulate JSON recursive structure better than 'Any'
# amount of repeated equivalent definition makes typing analysis 'work well enough' for most use cases
_JSON: TypeAlias = "JSON"
_JsonObjectItemAlias: TypeAlias = "_JsonObjectItem"
_JsonListItemAlias: TypeAlias = "_JsonListItem"
_JsonObjectItem = Dict[str, Union[_JSON, _JsonObjectItemAlias, _JsonListItemAlias]]
_JsonListItem = List[Union[AnyValueType, _JsonObjectItem, _JsonListItemAlias]]
_JsonItem = Union[AnyValueType, _JsonObjectItem, _JsonListItem, _JSON]
JSON = Union[Dict[str, _JsonItem], List[_JsonItem], AnyValueType]

# registered configurations
ConfigItem = Dict[str, JSON]
ConfigList = List[ConfigItem]
ConfigDict = Dict[str, Union[str, ConfigItem, ConfigList, JSON]]
ConfigResTokenInfo = TypedDict("ConfigResTokenInfo", {"has_multi_token": bool, "named_tokens": set})
ConfigSegment = TypedDict("ConfigSegment", {"name": str, "type": str})

ResourceSegment = TypedDict("ResourceSegment", {"resource_name": str, "resource_type": str})
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
