from copy import deepcopy

from celery import shared_task
from celery.exceptions import TimeoutError
from pyramid.httpexceptions import HTTPOk
from pyramid.security import NO_PERMISSION_REQUIRED
from pyramid.view import view_config

from cowbird import __meta__
from cowbird.api import exception as ax
from cowbird.api import schemas as s
from cowbird.constants import get_constant
from cowbird.utils import CONTENT_TYPE_JSON, get_logger

LOGGER = get_logger(__name__)


@s.HomepageAPI.get(tags=[s.APITag], api_security=s.SecurityEveryoneAPI, response_schemas=s.Homepage_GET_responses)
@view_config(route_name=s.HomepageAPI.name, request_method="GET", permission=NO_PERMISSION_REQUIRED)
def get_homepage(request):  # noqa: W0212
    """
    Cowbird API homepage.
    """
    body = deepcopy(s.InfoAPI)
    body.update({
        "title": s.TitleAPI,
        "name": __meta__.__package__,
        "documentation": get_constant("COWBIRD_URL", request) + s.SwaggerAPI.path
    })
    return ax.valid_http(http_success=HTTPOk, content=body, content_type=CONTENT_TYPE_JSON,
                         detail=s.Homepage_GET_OkResponseSchema.description)


@s.VersionAPI.get(tags=[s.APITag], api_security=s.SecurityEveryoneAPI, response_schemas=s.Version_GET_responses)
@view_config(route_name=s.VersionAPI.name, request_method="GET", permission=NO_PERMISSION_REQUIRED)
def get_version(request):  # noqa: W0212
    """
    Version of the API.
    """
    task = get_worker_version.delay()
    try:
        worker_version = task.get(timeout=2)
    except TimeoutError:
        worker_version = "worker unreachable"
    except NotImplementedError:
        worker_version = "unknown"  # TODO: Once we have a database, it could be used to store the jobs result
    version = {
        "version": __meta__.__version__,
        "worker_version": worker_version
    }
    return ax.valid_http(http_success=HTTPOk, content=version, content_type=CONTENT_TYPE_JSON,
                         detail=s.Version_GET_OkResponseSchema.description)


@shared_task()
def get_worker_version():
    return __meta__.__version__
