from copy import deepcopy

import celery.exceptions
from celery import shared_task
from pyramid.httpexceptions import HTTPFailedDependency, HTTPInternalServerError, HTTPOk
from pyramid.request import Request
from pyramid.security import NO_PERMISSION_REQUIRED
from pyramid.view import view_config

from cowbird import __meta__
from cowbird.api import exception as ax
from cowbird.api import schemas as s
from cowbird.constants import get_constant
from cowbird.typedefs import JSON, AnyResponseType
from cowbird.utils import CONTENT_TYPE_JSON, get_logger

LOGGER = get_logger(__name__)


@s.HomepageAPI.get(tags=[s.APITag], api_security=s.SecurityEveryoneAPI, response_schemas=s.Homepage_GET_responses)
@view_config(route_name=s.HomepageAPI.name, request_method="GET", permission=NO_PERMISSION_REQUIRED)
def get_homepage(request: Request) -> AnyResponseType:
    """
    Cowbird API homepage.
    """
    cowbird_url: str = get_constant("COWBIRD_URL", request)
    body = deepcopy(s.InfoAPI)
    body.update({
        "title": s.TitleAPI,
        "name": __meta__.__package__,
        "documentation": cowbird_url + s.SwaggerAPI.path
    })
    return ax.valid_http(http_success=HTTPOk, content=body, content_type=CONTENT_TYPE_JSON,
                         detail=s.Homepage_GET_OkResponseSchema.description)


@s.VersionAPI.get(tags=[s.APITag], api_security=s.SecurityEveryoneAPI, response_schemas=s.Version_GET_responses)
@view_config(route_name=s.VersionAPI.name, request_method="GET", permission=NO_PERMISSION_REQUIRED)
def get_version(request: Request) -> AnyResponseType:  # noqa: W0212
    """
    Version of the API.
    """
    http_class = HTTPFailedDependency
    http_detail = s.FailedDependencyErrorResponseSchema.description
    worker_version = None
    worker_detail = "unknown"
    try:
        task = get_worker_version.delay()
        worker_version = task.get(timeout=2)
        worker_detail = worker_version
        http_class = HTTPOk
        http_detail = s.Version_GET_OkResponseSchema.description
    except celery.exceptions.TimeoutError as exc:
        LOGGER.error("Failed retrieving worker version.", exc_info=exc)
        worker_detail = "worker unreachable"
    except NotImplementedError as exc:
        LOGGER.error("Failed retrieving worker version.", exc_info=exc)
    except Exception as exc:
        LOGGER.error("Error when trying to retrieve worker version.", exc_info=exc)
        http_class = HTTPInternalServerError
        http_detail = "Unhandled error when trying to retrieve worker version."
    api_version = __meta__.__version__
    detail = (
        f"Web service version : [{api_version}], worker version : [{worker_detail}]. "
        "Any mismatch can cause misbehavior."
    )
    version: JSON = {
        "version": api_version,
        "worker_version": worker_version,
        "version_detail": detail
    }
    if http_class is not HTTPOk:
        ax.raise_http(http_class, content=version, content_type=CONTENT_TYPE_JSON, detail=http_detail)
    return ax.valid_http(http_success=http_class, content=version, content_type=CONTENT_TYPE_JSON, detail=http_detail)


@shared_task()
def get_worker_version() -> str:
    return __meta__.__version__
