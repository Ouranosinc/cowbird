import celery.exceptions
import six
import pytest
import unittest
from unittest.mock import patch
from datetime import datetime
from time import sleep
from tests import utils
from celery import chain
from celery import shared_task
from celery.states import SUCCESS
from cowbird.request_task import RequestTask
from cowbird.services.service_factory import ServiceFactory
from cowbird.utils import SingletonMeta


"""
Helpful documentation on how to setup celery test fixtures:
https://medium.com/@scythargon/how-to-use-celery-pytest-fixtures-for-celery-intergration-testing-6d61c91775d9

TL;DR :
- Add a session fixture with an in-memory celery config
- Use the celery_session_app and celery_session_worker fixtures for the tests
- Don't forget to use the shared_task decorator instead of the usual app.task because shared_task use a proxy allowing 
  the task to be bound to any app (including the celery_session_app fixture). 
"""


@pytest.fixture(scope='session')
def celery_config():
    return {
        'broker_url': 'memory://',
        'result_backend': 'rpc'
    }


def get_timeout(task, timeout):
    """
    Replace the task.get(timeout=timeout) because this function timeout every time with rpc result_backend
    """
    for _ in range(timeout):
        if task.ready():
            return task.get()
        sleep(1)
    raise celery.exceptions.TimeoutError()


@shared_task(bind=True, base=RequestTask)
def sum_task(self, param1, param2):
    # type (int, int) -> int
    return param1 + param2


@six.add_metaclass(SingletonMeta)
class UnreliableTaskStats:
    """
    Hold unreliable task runtime stats
    """
    max_retries = 4

    def __init__(self):
        self.invoke_time = []

    def called(self):
        self.invoke_time.append(datetime.now())


@shared_task(bind=True, base=RequestTask)
def sum_unreliable_task(self, param1, param2):
    # type (int, int) -> int
    UnreliableTaskStats().called()
    if self.request.retries < UnreliableTaskStats.max_retries:
        raise Exception()
    return param1 + param2


@shared_task(bind=True, base=RequestTask)
def abort_sum_task(self, param1, param2):
    # type (int, int) -> int
    self.abort_chain()
    return param1 + param2


@pytest.mark.request_task
@pytest.mark.usefixtures('celery_session_app')
@pytest.mark.usefixtures('celery_session_worker')
class TestRequestTask(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = utils.get_test_app(settings={"cowbird.config_path": utils.TEST_CFG_FILE})

    @classmethod
    def tearDownClass(cls):
        utils.clear_services_instances()

    def test_chain(self):
        res = chain(sum_task.s(1, 2),
                    sum_task.s(3),
                    sum_task.s(6))
        task = res.delay()
        assert get_timeout(task, timeout=10) == 12
        assert task.status == SUCCESS

    def test_retrying(self):
        res = chain(sum_task.s(1, 2),
                    sum_unreliable_task.s(3),
                    sum_task.s(6))
        task = res.delay()

        assert get_timeout(task, timeout=60) == 12
        assert task.status == SUCCESS
        invoke_time = UnreliableTaskStats().invoke_time
        # Check number of retries
        assert len(invoke_time) == UnreliableTaskStats.max_retries + 1
        # Check backoff strategy
        assert (invoke_time[-1] - invoke_time[-2]) > (invoke_time[1] - invoke_time[0])

    def test_aborting(self):
        res = chain(sum_task.s(1, 2),
                    abort_sum_task.s(3),
                    sum_task.s(6))
        task = res.delay()
        # TODO: Test case still not working, aborting the chain leave the chain in pending state
        assert get_timeout(task, timeout=10) == 6
        assert task.status == SUCCESS

    @patch("cowbird.services.impl.geoserver.Geoserver.create_workspace")
    @patch("cowbird.services.impl.geoserver.Geoserver.create_datastore")
    def test_geoserver(self, create_datastore_mock, create_workspace_mock):
        test_user_name = "test_user"
        test_workspace_id = 1000
        create_workspace_mock.return_value = test_workspace_id
        geoserver = ServiceFactory().get_service("Geoserver")

        # geoserver should call create_workspace and then create_datastore
        geoserver.user_created(test_user_name)

        # current implementation doesn't give any handler on which we could wait
        sleep(2)

        create_workspace_mock.assert_called_with(test_user_name)
        # TODO: hard-coded "default" datastore name is based on the current demo implementation. Must be improved.
        create_datastore_mock.assert_called_with(test_workspace_id, "default")
