from abc import ABC

from celery import Task
from requests.exceptions import RequestException


class AbortException(Exception):
    """
    Exception raised when the chain must be interrupted.
    """


class RequestTask(Task, ABC):
    """
    Celery base task that should be used to handle API requests.

    Using this class will set the following Task configuration :
     - autoretry for every RequestException
     - backoff and jitter strategy
    There is also an abort_chain function to stop the chain of requests in case of an unrecoverable event

    To use this class simply decorate your asynchronous function like this :
        shared_task::

            @shared_task(bind=True, base=RequestTask)
            def function_name(self, any, wanted, parameters):

    bind=True will provide the self argument to the function which is the celery Task (not required)
    base=RequestTask will instantiate a RequestTask rather than a base celery Task as the self object
    """
    autoretry_for = (RequestException,)
    retry_backoff = True
    retry_backoff_max = 600  # Max backoff to 10 min
    retry_jitter = True
    retry_kwargs = {"max_retries": 15}

    def abort_chain(self):
        """
        Calling this function from a task will prevent any downstream tasks to be run after it.
        """
        raise AbortException("Aborting chain")
