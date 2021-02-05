from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List

    from cowbird.typedefs import AnySettingsContainer


class Service(object):
    def __init__(self, name):
        self.name = name

    def json(self):
        return {"name": self.name}


def get_services(container):
    # type: (AnySettingsContainer) -> List[Service]
    """
    Obtains the services managed by the application.
    """
    return [Service("test")]       # FIXME: implement
