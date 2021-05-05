from cowbird.services.service import Service


class Thredds(Service):
    """
    Nothing to do right now.
    """

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
