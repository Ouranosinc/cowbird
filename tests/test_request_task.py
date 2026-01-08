"""
Helpful documentation on how to setup celery test fixtures:

https://medium.com/@scythargon/6d61c91775d9

TL;DR :
- Add a session fixture with an in-memory celery config.
- Use the ``celery_session_app`` and ``celery_session_worker`` fixtures for the tests.
- Don't forget to use the shared_task decorator instead of the usual ``app.task`` because ``shared_task`` uses
  a proxy allowing the task to be bound to any app (including the ``celery_session_app`` fixture).
"""
import contextlib
import unittest
from abc import ABC
from datetime import datetime
from time import sleep
from unittest.mock import patch

import pytest
from celery import chain, shared_task
from celery.states import FAILURE, SUCCESS
from requests.exceptions import RequestException

from cowbird.handlers.impl.geoserver import Geoserver
from cowbird.request_task import AbortException, RequestTask
from tests import utils
from tests.utils import MockMagpieHandler


@pytest.fixture(scope="session")
def celery_config():
    return {
        "broker_url": "memory://",
        "result_backend": "cache+memory://"
    }


class UnreliableRequestTask(RequestTask, ABC):
    retry_jitter = False  # Turn off RequestTask.jitter to get reliable result
    test_max_retries = 3  # Max retries to be used by the test task
    invoke_time = []  # Log every call invocation

    def __call__(self, *args, **kwargs):
        UnreliableRequestTask.invoke_time.append(datetime.now())
        return self.run(*args, **kwargs)


@shared_task(bind=True, base=UnreliableRequestTask)
def unreliable_request_task(self: RequestTask, param1: int, param2: int) -> int:
    if self.request.retries < UnreliableRequestTask.test_max_retries:
        raise RequestException()
    return param1 + param2


@shared_task(bind=True, base=RequestTask)
def abort_sum_task(self: RequestTask, param1: int, param2: int) -> int:
    self.abort_chain()
    return param1 + param2


@shared_task(base=RequestTask)
def sum_task(param1: int, param2: int) -> int:
    return param1 + param2


@pytest.mark.request_task
@pytest.mark.usefixtures("celery_session_app")
@pytest.mark.usefixtures("celery_session_worker")
class TestRequestTask(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Reset handlers instances in case any are left from other test cases
        utils.clear_handlers_instances()

        cls.app = utils.get_test_app(settings={"cowbird.config_path": utils.TEST_CFG_FILE})

    @classmethod
    def tearDownClass(cls):
        utils.clear_handlers_instances()

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

    @pytest.mark.geoserver
    @patch("cowbird.handlers.impl.geoserver.Geoserver._create_datastore_dir")
    @patch("cowbird.handlers.impl.geoserver.Geoserver.create_datastore")
    @patch("cowbird.handlers.impl.geoserver.Geoserver.create_workspace")
    def test_geoserver_user_created(self, create_workspace_mock, create_datastore_mock, create_datastore_dir_mock):
        test_user_name = "test_user"
        geoserver = Geoserver.get_instance()

        # geoserver should call create_workspace and then create_datastore
        geoserver.user_created(test_user_name)

        # current implementation doesn't give any handler on which we could wait
        sleep(2)
        create_datastore_dir_mock.assert_called_with(test_user_name)
        create_workspace_mock.assert_called_with(test_user_name)
        create_datastore_mock.assert_called_with(test_user_name)

    @pytest.mark.geoserver
    @patch("cowbird.handlers.impl.geoserver.Geoserver._create_datastore_dir")
    @patch("cowbird.handlers.impl.geoserver.Geoserver._configure_datastore_request")
    @patch("cowbird.handlers.impl.geoserver.Geoserver._create_datastore_request")
    @patch("cowbird.handlers.impl.geoserver.Geoserver._create_workspace_request")
    def test_geoserver_workspace_datastore_created(self,
                                                   create_workspace_request_mock,
                                                   create_datastore_request_mock,
                                                   configure_datastore_request_mock,
                                                   _create_datastore_dir_mock):
        test_user_name = "test_user"
        test_datastore_name = f"shapefile_datastore_{test_user_name}"
        test_datastore_path = f"/user_workspaces/{test_user_name}/shapefile_datastore"
        geoserver = Geoserver.get_instance()

        # geoserver should call create_workspace and then create_datastore
        geoserver.user_created(test_user_name)

        # current implementation doesn't give any handler on which we could wait
        sleep(2)
        create_workspace_request_mock.assert_called_with(workspace_name=test_user_name)
        create_datastore_request_mock.assert_called_with(workspace_name=test_user_name,
                                                         datastore_name=test_datastore_name)
        configure_datastore_request_mock.assert_called_with(workspace_name=test_user_name,
                                                            datastore_name=test_datastore_name,
                                                            datastore_path=test_datastore_path)

    @pytest.mark.geoserver
    @patch("cowbird.handlers.impl.geoserver.Geoserver.remove_workspace")
    def test_geoserver_user_deleted(self, remove_workspace_mock):
        with contextlib.ExitStack() as stack:
            # Mocked Magpie required since deleting a user on Geoserver also deletes related Magpie resources
            stack.enter_context(patch("cowbird.handlers.impl.magpie.Magpie", side_effect=MockMagpieHandler))

            test_user_name = "test_user"
            geoserver = Geoserver.get_instance()
            geoserver.user_deleted(test_user_name)

            # current implementation doesn't give any handler on which we could wait
            sleep(2)

            remove_workspace_mock.assert_called_with(test_user_name)

    @pytest.mark.geoserver
    @patch("cowbird.handlers.impl.geoserver.Geoserver._remove_workspace_request")
    def test_geoserver_workspace_removed(self, remove_workspace_request_mock):
        with contextlib.ExitStack() as stack:
            # Mocked Magpie required since deleting a user on Geoserver also deletes related Magpie resources
            stack.enter_context(patch("cowbird.handlers.impl.magpie.Magpie", side_effect=MockMagpieHandler))

            test_user_name = "test_user"
            geoserver = Geoserver.get_instance()
            geoserver.user_deleted(test_user_name)

            # current implementation doesn't give any handler on which we could wait
            sleep(2)

            remove_workspace_request_mock.assert_called_with(workspace_name=test_user_name)

    @pytest.mark.geoserver
    @patch("cowbird.handlers.impl.geoserver.Geoserver._publish_shapefile_request")
    @patch("cowbird.handlers.impl.geoserver.Geoserver.validate_shapefile")
    def test_geoserver_file_creation(self, validate_shapefile_mock, publish_shapefile_request_mock):
        test_user_name = "test_user"
        shapefile_name = "test_shapefile"
        datastore_name = f"shapefile_datastore_{test_user_name}"

        # initialize geoserver instance
        Geoserver.get_instance()

        # geoserver should call create_workspace and then create_datastore
        Geoserver.publish_shapefile_task_chain(workspace_name=test_user_name, shapefile_name=shapefile_name)

        # current implementation doesn't give any handler on which we could wait
        sleep(2)
        validate_shapefile_mock.assert_called_with(test_user_name, shapefile_name)
        publish_shapefile_request_mock.assert_called_with(workspace_name=test_user_name,
                                                          datastore_name=datastore_name,
                                                          filename=shapefile_name)

    @pytest.mark.geoserver
    @patch("cowbird.handlers.impl.geoserver.Geoserver._remove_shapefile_request")
    def test_geoserver_file_removal(self, remove_shapefile_request_mock):
        test_user_name = "test_user"
        shapefile_name = "test_shapefile"
        datastore_name = f"shapefile_datastore_{test_user_name}"

        # initialize geoserver instance
        Geoserver.get_instance()

        # geoserver should call create_workspace and then create_datastore
        Geoserver.remove_shapefile_task(workspace_name=test_user_name, shapefile_name=shapefile_name)

        # current implementation doesn't give any handler on which we could wait
        sleep(2)
        remove_shapefile_request_mock.assert_called_with(workspace_name=test_user_name,
                                                         datastore_name=datastore_name,
                                                         filename=shapefile_name)
