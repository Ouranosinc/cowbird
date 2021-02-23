from cowbird.services.service import Service
from cowbird.requestqueue import RequestQueue


class Geoserver(Service):
    """
    Keep Geoserver internal representation in synch with the platform.

    Keep service-shared resources in synch when Geoserver permissions are
    updated.
    """
    def __init__(self, name):
        super(Geoserver, self).__init__(name)
        self.req_queue = RequestQueue()
