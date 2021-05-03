from cowbird.request_queue import RequestQueue
from cowbird.services.service import Service


class Geoserver(Service):
    """
    Keep Geoserver internal representation in synch with the platform.
    """

    def __init__(self, name, url):
        super(Geoserver, self).__init__(name, url)
        self.req_queue = RequestQueue()

    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        raise NotImplementedError

    def user_created(self, user_name):
        raise NotImplementedError

    def user_deleted(self, user_name):
        raise NotImplementedError

    def permission_created(self, permission):
        raise NotImplementedError

    def permission_deleted(self, permission):
        raise NotImplementedError
