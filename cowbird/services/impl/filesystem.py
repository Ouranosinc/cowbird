import os
import shutil

from cowbird.services.service import Service
from cowbird.services.service import (
    SERVICE_WORKSPACE_DIR_PARAM)
from cowbird.utils import get_logger

LOGGER = get_logger(__name__)


class FileSystem(Service):
    """
    Keep the proper directory structure in synch with the platform.
    """
    required_params = [SERVICE_WORKSPACE_DIR_PARAM]

    def __init__(self, name, **kwargs):
        super(FileSystem, self).__init__(name, **kwargs)

    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        raise NotImplementedError

    def user_created(self, user_name):
        os.mkdir(os.path.join(self.workspace_dir, user_name))

    def user_deleted(self, user_name):
        shutil.rmtree(os.path.join(self.workspace_dir, user_name))

    def permission_created(self, permission):
        raise NotImplementedError

    def permission_deleted(self, permission):
        raise NotImplementedError
