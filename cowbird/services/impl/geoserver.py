from cowbird.requestqueue import RequestQueue
from cowbird.services.service import Service


class Geoserver(Service):
    """
    Keep Geoserver internal representation in synch with the platform.
    """

    def __init__(self, name, url):
        super(Geoserver, self).__init__(name, url)
        self.req_queue = RequestQueue()
