from cowbird.permissions_synchronizer import PermissionSynchronizer
from cowbird.services.service import Service


class Magpie(Service):
    """
    Complete the Magpie's webhook call by calling Magpie temporary urls. Also keep service-shared resources in sync when
    permissions are updated for one of them.

    ** Cowbird components diagram 1.2.0 needs to be update since Magpie can
    handle permissions synchronisation directly on permission update events. No
    need to handle them explicitly in nginx, thredds and geoserver classes.
    """

    def __init__(self, name, url):
        super(Magpie, self).__init__(name, url)
        self.permissions_synch = PermissionSynchronizer()

    def create_permission(self, permission):
        self.permissions_synch.create_permission(permission)

    def delete_permission(self, permission):
        self.permissions_synch.delete_permission(permission)
