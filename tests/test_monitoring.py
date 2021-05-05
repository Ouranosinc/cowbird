import os
import tempfile
from time import sleep

import pytest

from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring


def file_io(filename, mv_filename):
    # Create
    with open(filename, "w") as f:
        f.write("Hello")
    # Update
    with open(filename, "a") as f:
        f.write(" world!")
    # Should create a delete and a create event
    os.rename(filename, mv_filename)
    # Delete
    os.remove(mv_filename)


@pytest.mark.monitoring
def test_register_unregister_monitor():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "testfile")
        test_subdir = os.path.join(tmpdir, "subdir")
        test_subdir_file = os.path.join(test_subdir, "test_subdir_file")
        mv_test_file = os.path.join(test_subdir, "moved_testfile")
        mv_test_subdir_file = os.path.join(tmpdir, "moved_test_subdir_file")
        os.mkdir(test_subdir)

        mon = TestMonitor()
        mon2 = TestMonitor()
        mon3 = TestMonitor()
        Monitoring().register(tmpdir, False, mon)
        Monitoring().register(tmpdir, True, mon2)
        Monitoring().register(test_subdir, True, mon3)
        assert len(Monitoring().monitors) == 2
        assert len(Monitoring().monitors[tmpdir]) == 2

        file_io(test_file, mv_test_file)
        file_io(test_subdir_file, mv_test_subdir_file)

        sleep(1)
        # Root dir non-recursive
        assert len(mon.created) == 2
        assert mon.created[0] == test_file
        assert mon.created[1] == mv_test_subdir_file
        assert mon.created == mon.deleted
        assert sorted(set(mon.modified)) == [tmpdir, test_file]

        # Root dir recursive
        assert len(mon2.created) == 4
        assert mon2.created[0] == test_file
        assert mon2.created[1] == mv_test_file
        assert mon2.created[2] == test_subdir_file
        assert mon2.created[3] == mv_test_subdir_file
        assert mon2.created == mon2.deleted
        assert sorted(set(mon2.modified)) == [tmpdir, test_subdir,
                                              test_subdir_file, test_file]

        # Subdir
        assert len(mon3.created) == 2
        assert mon3.created[0] == mv_test_file
        assert mon3.created[1] == test_subdir_file
        assert mon3.created == mon3.deleted
        assert sorted(set(mon3.modified)) == [test_subdir,
                                              test_subdir_file]

        Monitoring().unregister(tmpdir, mon)
        Monitoring().unregister(tmpdir, mon2)
        assert not Monitoring().unregister(test_subdir, mon)
        Monitoring().unregister(test_subdir, mon3)
        assert len(Monitoring().monitors) == 0
        assert not Monitoring().unregister(tmpdir, mon)


class TestMonitor(FSMonitor):
    def __init__(self):
        self.created = []
        self.deleted = []
        self.modified = []

    def on_created(self, filename):
        self.created.append(filename)

    def on_deleted(self, filename):
        self.deleted.append(filename)

    def on_modified(self, filename):
        self.modified.append(filename)
