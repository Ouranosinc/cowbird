

class Service(object):
    """
    Service interface use to notify implemented services of users/permissions changes.

    TODO: At some point we will need a consistency function that goes through all Magpie users and make sure that
          services are up to date.
    """

    def __init__(self, name, url=None):
        self.name = name
        self.url = url

    def json(self):
        return {"name": self.name, "url": self.url}

    def get_resource_id(self, resource_full_name):
        # type (str) -> str
        """
        Each service must provide this implementation required by the permission synchronizer.

        The function needs to find the resource id in Magpie from the resource full name using its knowledge of the
        service. If the resource doesn't already exist, the function needs to create it, again using its knowledge of
        resource type and parent resource type if required.
        """
        # TODO implement it for every service

    def user_created(self, user_name):
        pass

    def user_deleted(self, user_name):
        pass

    def permission_created(self, permission):
        pass

    def permission_deleted(self, permission):
        pass
