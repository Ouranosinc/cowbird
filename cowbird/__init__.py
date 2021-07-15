# -*- coding: utf-8 -*-
import sys

# NOTE:
#   Do not import anything here that is not part of the python standard library.
#   Any external package could still not yet be installed when importing the package
#   to access high-level information such as the metadata (__meta__.py).


def includeme(config):
    # import needs to be here, otherwise ImportError happens during setup.py install (modules not yet installed)
    # pylint: disable=C0415
    from pyramid.events import NewRequest
    from pyramid.tweens import EXCVIEW

    from cowbird.api import generic as ag
    from cowbird.constants import get_constant
    from cowbird.utils import fully_qualified_name, get_logger, log_exception_tween, log_request

    mod_dir = get_constant("COWBIRD_MODULE_DIR", config)
    logger = get_logger(__name__)
    logger.info("Adding COWBIRD_MODULE_DIR='%s' to path.", mod_dir)
    sys.path.insert(0, mod_dir)

    config.add_exception_view(ag.internal_server_error)
    config.add_notfound_view(RemoveSlashNotFoundViewFactory(ag.not_found_or_method_not_allowed), append_slash=True)

    tween_position = fully_qualified_name(ag.apply_response_format_tween)
    config.add_tween(tween_position, over=EXCVIEW)
    if get_constant("COWBIRD_LOG_REQUEST", config):
        config.add_subscriber(log_request, NewRequest)
    if get_constant("COWBIRD_LOG_EXCEPTION", config):
        tween_name = fully_qualified_name(log_exception_tween)
        config.add_tween(tween_name, under=tween_position)
        tween_position = tween_name
    config.add_tween(fully_qualified_name(ag.validate_accept_header_tween), under=tween_position)

    config.include("cornice")
    config.include("cornice_swagger")
    config.include("cowbird.api")
    config.include("cowbird.database")


class RemoveSlashNotFoundViewFactory(object):
    """
    Utility that will try to resolve a path without appended slash if one was provided.
    """

    def __init__(self, notfound_view=None):
        self.notfound_view = notfound_view

    def __call__(self, request):
        from pyramid.httpexceptions import HTTPMovedPermanently
        from pyramid.interfaces import IRoutesMapper
        path = request.path
        registry = request.registry
        mapper = registry.queryUtility(IRoutesMapper)
        if mapper is not None and path.endswith("/"):
            no_slash_path = path.rstrip("/")
            no_slash_path = no_slash_path.split("/cowbird", 1)[-1]
            for route in mapper.get_routes():
                if route.match(no_slash_path) is not None:
                    query = request.query_string
                    if query:
                        no_slash_path += "?" + query
                    return HTTPMovedPermanently(location=no_slash_path)
        return self.notfound_view(request)
