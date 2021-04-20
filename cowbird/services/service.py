

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

    def create_user(self, username):
        pass

    def delete_user(self, username):
        pass

    def create_permission(self, permission):
        pass

    def delete_permission(self, permission):
        pass
