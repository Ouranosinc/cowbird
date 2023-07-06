from abc import ABC
from typing import TYPE_CHECKING

from celery.app.task import Task
from requests.exceptions import RequestException

if TYPE_CHECKING:
    from typing import Tuple


class AbortException(Exception):
    """
    Exception raised when the chain must be interrupted.
    """


class RequestTask(Task, ABC):
    """
    Celery base task that should be used to handle API requests.

    Using this class will set the following Task configuration :
     - auto-retry for every RequestException
     - backoff and jitter strategy

    There is also an abort_chain function to stop the chain of requests in case of an unrecoverable event

    To use this class simply decorate your asynchronous function like this:

    .. code-block:: python

        from celery import shared_task

        @shared_task(bind=True, base=RequestTask)
        def function_name(self, any, wanted, parameters):
            pass  # function operations

    Parameter ``bind=True`` will provide the self argument to the function which is the celery Task (not required).

    Parameter ``base=RequestTask`` will instantiate a RequestTask rather than a base celery Task as the self object.
    """

    autoretry_for = (RequestException,)  # type: Tuple[Exception]
    """
    Exceptions that are accepted as valid raising cases to attempt request retry.
    """

    retry_backoff = True
    """
    Enable backoff strategy during request retry upon known raised exception.
    """

    retry_backoff_max = 600  # Max backoff to 10 min
    """
    Maximum backoff delay permitted using request retry.

    Retries are abandoned if this delay is reached.
    """

    retry_jitter = True
    """
    Enable jitter strategy during request retry upon known raised exception.
    """

    retry_kwargs = {"max_retries": 15}
    """
    Additional parameters to be passed down to requests for retry control.
    """

    def abort_chain(self):
        """
        Calling this function from a task will prevent any downstream tasks to be run after it.
        """
        raise AbortException("Aborting chain")
