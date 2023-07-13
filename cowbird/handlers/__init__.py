
from typing import List, Optional

from cowbird.handlers.handler import Handler
from cowbird.handlers.handler_factory import HandlerFactory
from cowbird.typedefs import AnySettingsContainer


def get_handlers(container: Optional[AnySettingsContainer] = None) -> List[Handler]:
    """
    Obtains the handlers managed by the application.
    """
    return HandlerFactory().get_active_handlers()
