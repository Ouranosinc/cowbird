#!/usr/bin/env python
"""
Additional typing definitions.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Dict, List, Tuple, Type, TypedDict, Union

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

    AnyKey = Union[str, int]
    AnyValue = Union[str, Number, bool, None]
    BaseJSON = Union[AnyValue, List["BaseJSON"], Dict[AnyKey, "BaseJSON"]]
    JSON = Union[Dict[AnyKey, Union[BaseJSON, "JSON"]], List[BaseJSON]]

    # registered configurations
    ConfigItem = Dict[str, JSON]
    ConfigList = List[ConfigItem]
    ConfigDict = Dict[str, Union[str, ConfigItem, ConfigList, JSON]]
    ConfigResTokenInfo = TypedDict("ConfigResTokenInfo", {"has_multi_token": bool, "named_tokens": set})
    ConfigSegment = TypedDict("ConfigSegment", {"name": str, "type": str})

    ResourceSegment = TypedDict("ResourceSegment", {"resource_name": str, "resource_type": str})
    PermissionDataEntry = TypedDict("PermissionDataEntry",
                                    {"res_path": List[ResourceSegment], "permissions": Dict[str, List[str]]})
    PermissionData = Dict[str, PermissionDataEntry]

    from cowbird.database.stores import StoreInterface
    StoreSelector = Union[Type[StoreInterface], StoreInterface, str]
