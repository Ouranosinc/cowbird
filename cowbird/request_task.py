from celery import Task


class RequestTask(Task):
    """
    Handle API requests queue.

    .. todo:: Connect to celery queue to submit request in an async manner
    See https://github.com/celery/celery/issues/3744#issuecomment-271366923 for class registration
    """
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600  # Max backoff to 10 min
    retry_jitter = True
    retry_kwargs = {'max_retries': 15}

    def run(self, *args, **kwargs):
        """The body of the task executed by workers."""
        raise NotImplementedError('Tasks must define the run method.')

    def abort_chain(self):
        # TODO: Useful?
        # TODO: What to do with already completed tasks? Rollback?
        #       If they are idempotent then it's not useful. If we redo them, for exemple create something,
        #       it will first check for existence and not crash if it does.
        self.request.callbacks = None
