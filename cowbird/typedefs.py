#!/usr/bin/env python
"""
Additional typing definitions.
"""

from typing import TYPE_CHECKING

import six

if TYPE_CHECKING:
    from typing import Any, Dict, List, Tuple, Union

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

    if six.PY2:
        # pylint: disable=E0602,undefined-variable  # unicode not recognized by python 3
        Str = Union[AnyStr, unicode]  # noqa: E0602,F405,F821
    else:
        Str = str
