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
    MutableSet,
    Optional,
    Tuple,
    Type,
    TypedDict,
    Union
)
from typing_extensions import NotRequired, TypeAlias

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
    from magpie.typedefs import PermissionAction, PermissionConfigItem, PermissionDict
    from webtest.response import TestResponse  # only with install-dev

    from cowbird.database.stores import StoreInterface

# FIXME:
#   magpie still uses type-comments with TYPE_CHECKING guard
#   use the direct typing annotations when made available
#   following works, but type hints will be even better if using actual annotations
PermissionActionType: TypeAlias = "PermissionAction"
PermissionConfigItemType: TypeAlias = "PermissionConfigItem"
PermissionDictType: TypeAlias = "PermissionDict"

StoreInterfaceType: TypeAlias = "StoreInterface"
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
#   or 'AnyValueType', this can cause a lot of false positives typing detections. Sometimes, it is better
#   to provide the explicit type expected (e.g.: 'List[JSON]') when a specific structure is required to
#   disambiguate some situations.
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

HandlerConfig = TypedDict(
    "HandlerConfig",
    {
        # minimal needed to indicate if the handler should be active
        "active": bool,
        # optional settings shared by all handlers
        "priority": NotRequired[int],
        "url": NotRequired[str],
        # specific settings for distinct handlers, some shared
        "workspace_dir": NotRequired[str],
        "admin_user": NotRequired[str],
        "admin_password": NotRequired[str],
        "jupyterhub_user_data_dir": NotRequired[str],
        "wps_outputs_dir": NotRequired[str],
        "secure_data_proxy_name": NotRequired[str],
        "notebooks_dir_name": NotRequired[str],
        "public_workspace_wps_outputs_subpath": NotRequired[str],
        "user_wps_outputs_dir_name": NotRequired[str],
    },
    total=True,
)

# registered configurations
ConfigItem = Dict[str, JSON]
ConfigList = List[ConfigItem]
ConfigDict = Dict[str, Union[str, ConfigItem, ConfigList, JSON]]
ConfigResTokenInfo = TypedDict("ConfigResTokenInfo", {"has_multi_token": bool, "named_tokens": MutableSet[str]})
ConfigSegment = TypedDict("ConfigSegment", {"name": str, "type": str})

SyncPointMappingType = List[str]
SyncPointServicesType = Dict[
    str,  # service type
    Dict[
        str,  # resource key
        List[ConfigSegment],
    ]
]
SyncPermissionConfig = TypedDict(
    "SyncPermissionConfig",
    {
        "services": SyncPointServicesType,
        "permissions_mapping": SyncPointMappingType,
    },
    total=True,
)
SyncPointConfig = Dict[
    str,  # friendly name of sync point
    SyncPermissionConfig,
]

ResourceSegment = TypedDict("ResourceSegment", {"resource_name": str, "resource_type": str})
ResourceTree = List[
    Dict[
        str,
        # FIXME: replace by a more specific type provided by Magpie directly if eventually implemented
        #   Only partial fields are provided below (resource_name/resource_type),
        #   because those are the only ones used for now in Cowbird's sync operation.
        #   This actually contains more details such as the resource ID, permission names, etc.
        #   (see the response body of 'GET /magpie/resources/{resource_id}' for exact content).
        ResourceSegment,
    ]
]
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
