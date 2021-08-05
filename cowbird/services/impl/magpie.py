from cowbird.permissions_synchronizer import Permission, PermissionSynchronizer
from cowbird.services.service import SERVICE_URL_PARAM, Service


class Magpie(Service):
    """
    Complete the Magpie's webhook call by calling Magpie temporary urls. Also keep service-shared resources in sync when
    permissions are updated for one of them.

    ** Cowbird components diagram 1.2.0 needs to be update since Magpie can
    handle permissions synchronisation directly on permission update events. No
    need to handle them explicitly in nginx, thredds and geoserver classes.
    """
    required_params = [SERVICE_URL_PARAM]

    def __init__(self, name, **kwargs):
        # type: (str, dict) -> None
        """
        Create the magpie instance and instantiate the permission synchronizer that will handle the permission events.

        @param name: Service name
        """
        super(Magpie, self).__init__(name, **kwargs)
        self.permissions_synch = PermissionSynchronizer(self)

    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        raise NotImplementedError

    def user_created(self, user_name):
        raise NotImplementedError

    def user_deleted(self, user_name):
        raise NotImplementedError

    def permission_created(self, permission):
        self.permissions_synch.create_permission(permission)

    def permission_deleted(self, permission):
        self.permissions_synch.delete_permission(permission)

    def create_permission(self, permission):
        # type: (Permission) -> None
        """
        Make sure that the specified permission exists on Magpie.

        .. todo:: First need to check if the permission already exists
                  If the permission doesn't exist do a POST to create it
                  If the permission exists but is different do a PUT to update it
        """

    def delete_permission(self, permission):
        # type: (Permission) -> None
        """
        Remove the specified permission from Magpie if it exists.
        """
        # TODO: Post a DELETE request, handle error silently if the permission doesn't exist
