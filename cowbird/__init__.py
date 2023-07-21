# -*- coding: utf-8 -*-
import sys
from typing import TYPE_CHECKING

# NOTE:
#   Do not import anything here that is not part of the python standard library.
#   Any external package could still not yet be installed when importing the package
#   to access high-level information such as the metadata (__meta__.py).

if TYPE_CHECKING:
    # Although guarded by type checking, typing references can only use typing aliases with
    # quoted strings in function signature. Otherwise, the same issue as described above can occur.
    from pyramid.config import Configurator  # noqa


def includeme(config: "Configurator") -> None:
    # import needs to be here, otherwise ImportError happens during setup.py install (modules not yet installed)
    # pylint: disable=C0415
    from pyramid.events import NewRequest
    from pyramid.tweens import EXCVIEW

    from cowbird.api import generic as ag
    from cowbird.api.generic import RemoveSlashNotFoundViewFactory
    from cowbird.constants import get_constant
    from cowbird.utils import fully_qualified_name, get_logger, log_exception_tween, log_request

    mod_dir: str = get_constant("COWBIRD_MODULE_DIR", config)
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
