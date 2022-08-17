import os
import tempfile
import unittest

import mock
import pytest
import yaml
from pymongo.collection import Collection
from pymongo.cursor import Cursor

from cowbird.database.mongodb import MongoDatabase
from cowbird.database.stores import MonitoringStore
from cowbird.monitoring.monitor import Monitor
from tests import utils


@pytest.mark.database
class MongodbServiceStoreTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)  # pylint: disable=R1732
        with cls.cfg_file as f:
            f.write(yaml.safe_dump(
                {"handlers": {"Catalog": {"active": True, "url": "http://catalog", "workspace_dir": "/workspace"}}}))
        cls.app = utils.get_test_app(settings={"cowbird.config_path": cls.cfg_file.name})

    @classmethod
    def tearDownClass(cls):
        utils.clear_handlers_instances()
        os.unlink(cls.cfg_file.name)

    def setUp(self):
        self.monitor_params = dict(path="/", recursive=False, callback="cowbird.handlers.impl.catalog.Catalog")
        self.monitor_params_bad_path = dict(path="", recursive=False, callback="cowbird.handlers.impl.catalog.Catalog")
        self.monitor_params_bad_callback = dict(path="/", recursive=False, callback="")
        self.monitor = Monitor(**self.monitor_params)

    @pytest.mark.database
    def test_get_store(self):
        collection_mock = mock.Mock(spec=Collection)
        store_mock = MonitoringStore(collection=collection_mock)
        db = MongoDatabase({})
        store_t1 = db.get_store(store_mock)
        store_t2 = db.get_store(MonitoringStore)
        store_t3 = db.get_store(MonitoringStore.type)
        assert isinstance(store_t1, MonitoringStore)
        assert isinstance(store_t2, MonitoringStore)
        assert isinstance(store_t3, MonitoringStore)

    def test_save_monitor(self):
        collection_mock = mock.Mock(spec=Collection)
        collection_mock.count_documents.return_value = 1
        store = MonitoringStore(collection=collection_mock)
        store.save_monitor(self.monitor)

        collection_mock.delete_one.assert_called_with(self.monitor.key)
        collection_mock.insert_one.assert_called_with(self.monitor.params())

    def test_delete_monitor(self):
        collection_mock = mock.Mock(spec=Collection)
        store = MonitoringStore(collection=collection_mock)
        store.delete_monitor(self.monitor)

        collection_mock.delete_one.assert_called_with(self.monitor.key)

    def test_list_monitors(self):
        cursor_mock = mock.Mock(spec=Cursor)
        cursor_mock.sort.return_value = [self.monitor_params,
                                         self.monitor_params_bad_path,
                                         self.monitor_params_bad_callback]
        collection_mock = mock.Mock(spec=Collection)
        collection_mock.find.return_value = cursor_mock
        store = MonitoringStore(collection=collection_mock)
        monitors = store.list_monitors()
        assert len(monitors) == 1
        assert monitors[0].params() == self.monitor_params

        # Store should remove monitors with bad parameters from database
        collection_mock.delete_one.assert_has_calls([mock.call(self.monitor_params_bad_path),
                                                     mock.call(self.monitor_params_bad_callback)])
