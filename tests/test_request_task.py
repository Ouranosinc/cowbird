import mock
import pytest
import unittest
from unittest.mock import patch
from time import sleep
from tests import utils
from cowbird.utils import SingletonMeta
from cowbird.services.service_factory import ServiceFactory

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
