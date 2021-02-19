from cowbird.services.service import Service
from cowbird.requestqueue import RequestQueue


class Catalog(Service):
    """
    Keep the catalog index in synch when files are created/deleted/updated
    """
    def __init__(self, name):
        super(Catalog, self).__init__(name)
        self.req_queue = RequestQueue()
