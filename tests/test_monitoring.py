import os
import tempfile
import unittest
from time import sleep

import pytest
import yaml

from cowbird.handlers.handler_factory import HandlerFactory
from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring
from tests import utils


def file_io(filename, mv_filename):
    # Create
    with open(filename, "w", encoding="utf-8") as f:
        f.write("Hello")
    # Update
    with open(filename, "a", encoding="utf-8") as f:
        f.write(" world!")
    # Update on file permissions should also trigger a modified event
    os.chmod(filename, 0o777)
    # Should create a delete and a create event
    os.rename(filename, mv_filename)
    # Delete
    os.remove(mv_filename)


@pytest.mark.monitoring
class TestMonitoring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)  # pylint: disable=R1732
        with cls.cfg_file as f:
            f.write(yaml.safe_dump({"handlers": {"FileSystem": {"active": True, "workspace_dir": "/workspace"}}}))
        cls.app = utils.get_test_app(settings={"cowbird.config_path": cls.cfg_file.name})
        # clear up monitor entries from db
        Monitoring().store.collection.remove({})

    @classmethod
    def tearDownClass(cls):
        Monitoring().store.clear_services()
        utils.clear_handlers_instances()
        os.unlink(cls.cfg_file.name)

    def test_register_unregister_monitor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "testfile")
            test_subdir = os.path.join(tmpdir, "subdir")
            test_subdir_file = os.path.join(test_subdir, "test_subdir_file")
            mv_test_file = os.path.join(test_subdir, "moved_testfile")
            mv_test_subdir_file = os.path.join(tmpdir, "moved_test_subdir_file")
            os.mkdir(test_subdir)

            # Test registering directly a callback instance
            mon = TestMonitor()
            internal_mon = Monitoring().register(tmpdir, False, mon)
            assert internal_mon.callback_instance == mon

            # Test registering a callback via class name
            internal_mon2 = Monitoring().register(tmpdir, True, TestMonitor2)
            mon2 = internal_mon2.callback_instance
            internal_mon3 = Monitoring().register(test_subdir, False, TestMonitor)
            mon3 = internal_mon3.callback_instance
            assert isinstance(mon2, TestMonitor2)
            assert isinstance(mon3, TestMonitor)

            # Test collision when 2 monitors are registered using the same path and class name
            assert not internal_mon3.recursive
            internal_mon4 = Monitoring().register(test_subdir, True, TestMonitor)
            assert internal_mon4 is internal_mon3
            assert internal_mon3.recursive  # Recursive should take precedence when a collision occurs

            # monitors first level is distinct path to monitor : (tmp_dir and test_subdir)
            assert len(Monitoring().monitors) == 2

            # monitors second level is distinct callback, for tmpdir : (TestMonitor and TestMonitor2)
            assert len(Monitoring().monitors[tmpdir]) == 2

            # Do some io operations that should be picked by the monitors
            file_io(test_file, mv_test_file)
            file_io(test_subdir_file, mv_test_subdir_file)
            sleep(1)

            # Root dir non-recursive
            assert len(mon.created) == 2
            assert mon.created[0] == test_file
            assert mon.created[1] == mv_test_subdir_file
            assert mon.created == mon.deleted
            assert sorted(set(mon.modified)) == [tmpdir, test_file]
            assert len(mon.modified) == 9

            # Root dir recursive
            assert len(mon2.created) == 4
            assert mon2.created[0] == test_file
            assert mon2.created[1] == mv_test_file
            assert mon2.created[2] == test_subdir_file
            assert mon2.created[3] == mv_test_subdir_file
            assert mon2.created == mon2.deleted
            assert sorted(set(mon2.modified)) == [tmpdir, test_subdir,
                                                  test_subdir_file, test_file]
            assert len(mon2.modified) == 18

            # Subdir
            assert len(mon3.created) == 2
            assert mon3.created[0] == mv_test_file
            assert mon3.created[1] == test_subdir_file
            assert mon3.created == mon3.deleted
            assert sorted(set(mon3.modified)) == [test_subdir,
                                                  test_subdir_file]
            assert len(mon3.modified) == 9

            # Validate cleanup
            Monitoring().unregister(tmpdir, mon)
            Monitoring().unregister(tmpdir, mon2)
            # Here we try to unregister a path with a bad class type
            assert not Monitoring().unregister(test_subdir, mon2)
            # Here we have the good class type
            Monitoring().unregister(test_subdir, mon3)
            assert len(Monitoring().monitors) == 0
            assert not Monitoring().unregister(tmpdir, mon)

            # Test registering a callback via a qualified class name string
            catalog_mon = \
                Monitoring().register(tmpdir, False, "cowbird.handlers.impl.catalog.Catalog").callback_instance
            assert catalog_mon == HandlerFactory().get_handler("Catalog")


class TestMonitor(FSMonitor):
    def __init__(self):
        self.created = []
        self.deleted = []
        self.modified = []

    @staticmethod
    def get_instance():
        return TestMonitor()

    def on_created(self, path):
        self.created.append(path)

    def on_deleted(self, path):
        self.deleted.append(path)

    def on_modified(self, path):
        self.modified.append(path)


class TestMonitor2(TestMonitor):
    # Allow a second full qualified class name to register as monitor
    @staticmethod
    def get_instance():
        return TestMonitor2()
