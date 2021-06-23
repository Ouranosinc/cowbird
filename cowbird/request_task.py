from celery import Task


class RequestTask(Task):
    """
    Celery base task that should be used to handle API requests.

    To inherit of the propre configuration (autoretry, backoff and jitter strategy) simply decorate your asynchrone
    function like this :

    @shared_task(bind=True, base=RequestTask)
    def function_name(self, any, wanted, parameters):

    bind=True will provide the self argument to the function which is the celery Task
    base=RequestTask will instantiate a RequestTask rather than a base celery Task as the self object
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
        """
        Calling this function from a task will prevent any downstream tasks to be run after it but still report success.
        """
        # TODO: Not working, maybe just raising some exception?
        # TODO: What should we do with previous completed tasks? It will leave the service in a bad state...
        self.request.chain = None
