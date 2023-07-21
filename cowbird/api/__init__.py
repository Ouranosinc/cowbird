import os

from pyramid.config import Configurator

from cowbird.utils import get_logger


def includeme(config: Configurator) -> None:
    """
    Include API sub-modules.

    Each should define an ``includeme`` function with further sub-modules
    to include, and every one of their relative views and routes.
    """
    logger = get_logger(__name__)
    logger.info("Adding API routes...")
    cur_dir = os.path.dirname(__file__)
    for mod_name in os.listdir(cur_dir):
        mod_path = os.path.join(cur_dir, mod_name)
        mod_init = os.path.join(mod_path, "__init__.py")
        if os.path.isdir(mod_path) and os.path.isfile(mod_init):
            config.include(f"cowbird.api.{mod_name}")
