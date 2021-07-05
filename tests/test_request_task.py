"""
Helpful documentation on how to setup celery test fixtures:

https://medium.com/@scythargon/how-to-use-celery-pytest-fixtures-for-celery-intergration-testing-6d61c91775d9.

TL;DR :
- Add a session fixture with an in-memory celery config
- Use the celery_session_app and celery_session_worker fixtures for the tests
- Don't forget to use the shared_task decorator instead of the usual app.task because shared_task use a proxy allowing
  the task to be bound to any app (including the celery_session_app fixture).
"""
import unittest
from abc import ABC
from datetime import datetime
from time import sleep
from unittest.mock import patch

import pytest
from celery import chain, shared_task
from celery.states import FAILURE, SUCCESS
from requests.exceptions import RequestException

from cowbird.request_task import AbortException, RequestTask
from cowbird.services.service_factory import ServiceFactory
from tests import utils


@pytest.fixture(scope="session")
def celery_config():
    return {
        "broker_url": "memory://",
        "result_backend": "cache+memory://"
    }


class UnreliableRequestTask(RequestTask, ABC):
    retry_jitter = False  # Turn off RequestTask.jitter to get reliable result
    test_max_retries = 3  # Max retries to be used by the test task
    invoke_time = []      # Log every call invocation

    def __call__(self, *args, **kwargs):
        UnreliableRequestTask.invoke_time.append(datetime.now())
        return self.run(*args, **kwargs)


@shared_task(bind=True, base=UnreliableRequestTask)
def unreliable_request_task(self, param1, param2):
    # type (int, int) -> int
    if self.request.retries < UnreliableRequestTask.test_max_retries:
        raise RequestException()
    return param1 + param2


@shared_task(bind=True, base=RequestTask)
def abort_sum_task(self, param1, param2):
    # type (int, int) -> int
    self.abort_chain()
    return param1 + param2


@shared_task(base=RequestTask)
def sum_task(param1, param2):
    # type (int, int) -> int
    return param1 + param2


@pytest.mark.request_task
@pytest.mark.usefixtures("celery_session_app")
@pytest.mark.usefixtures("celery_session_worker")
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
        assert task.get(timeout=5) == 12
        assert task.status == SUCCESS

    def test_retrying(self):
        res = chain(sum_task.s(1, 2),
                    unreliable_request_task.s(3),
                    sum_task.s(6))
        task = res.delay()
        assert task.get(timeout=20) == 12
        assert task.status == SUCCESS
        invoke_time = UnreliableRequestTask.invoke_time
        # Check number of retries
        assert len(invoke_time) == UnreliableRequestTask.test_max_retries + 1
        # Check backoff strategy
        assert (invoke_time[-1] - invoke_time[-2]) > (invoke_time[1] - invoke_time[0])

    def test_aborting(self):
        res = chain(sum_task.s(1, 2),
                    abort_sum_task.s(3),
                    sum_task.s(6))
        task = res.delay()
        with pytest.raises(AbortException):
            task.get(timeout=5)
        assert task.status == FAILURE

    @patch("cowbird.services.impl.geoserver.Geoserver.create_workspace")
    @patch("cowbird.services.impl.geoserver.Geoserver.create_datastore")
    def test_geoserver(self, create_datastore_mock, create_workspace_mock):
        test_user_name = "test_user"
        test_workspace_id = 1000
        test_datastore_id = 1000
        create_workspace_mock.return_value = test_workspace_id
        create_datastore_mock.return_value = test_datastore_id
        geoserver = ServiceFactory().get_service("Geoserver")

        # geoserver should call create_workspace and then create_datastore
        geoserver.user_created(test_user_name)

        # current implementation doesn't give any handler on which we could wait
        sleep(2)

        create_workspace_mock.assert_called_with(test_user_name)
        # TODO: hard-coded "default" datastore name is based on the current demo implementation. Must be improved.
        create_datastore_mock.assert_called_with(test_workspace_id, "default")
