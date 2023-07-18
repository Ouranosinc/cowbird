import logging
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import yaml
from dotenv import load_dotenv
from webtest.app import TestApp

from cowbird.handlers import HandlerFactory
from cowbird.handlers.impl.filesystem import NOTEBOOKS_DIR_NAME
from cowbird.monitoring.monitoring import Monitoring
from tests import test_magpie
from tests import utils

if TYPE_CHECKING:
    from cowbird.typedefs import JSON

CURR_DIR = Path(__file__).resolve().parent


@pytest.mark.filesystem
class TestFileSystem(unittest.TestCase):
    """
    Test FileSystem operations.
    """

    @classmethod
    def setUpClass(cls):
        cls.jupyterhub_user_data_dir = "/jupyterhub_user_data"
        cls.test_username = "test_username"
        cls.callback_url = "callback_url"

        # Mock monitoring to disable monitoring events and to trigger file events manually instead during tests.
        cls.patcher = patch("cowbird.monitoring.monitoring.Monitoring.register")
        cls.mock_register = cls.patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    def setUp(self):
        self.test_directory = tempfile.TemporaryDirectory()
        self.workspace_dir = os.path.join(self.test_directory.name, "user_workspaces")
        self.wpsoutputs_dir = os.path.join(self.test_directory.name, "wpsoutputs")
        os.mkdir(self.workspace_dir)
        os.mkdir(self.wpsoutputs_dir)

        self.user_workspace_dir = Path(self.workspace_dir) / self.test_username

    def tearDown(self):
        utils.clear_handlers_instances()
        self.test_directory.cleanup()

    def get_test_app(self, cfg_data):
        # type: (JSON) -> TestApp
        cfg_file = os.path.join(self.test_directory.name, "config.yml")
        with open(cfg_file, "w") as f:
            f.write(yaml.safe_dump(cfg_data))
        utils.clear_handlers_instances()
        app = utils.get_test_app(settings={"cowbird.config_path": cfg_file})
        return app

    @patch("cowbird.api.webhooks.views.requests.head")
    def test_manage_user_workspace(self, mock_head_request):
        """
        Tests creating and deleting a user workspace.
        """
        user_symlink = self.user_workspace_dir / NOTEBOOKS_DIR_NAME
        app = self.get_test_app({
            "handlers": {
                "FileSystem": {
                    "active": True,
                    "workspace_dir": self.workspace_dir,
                    "jupyterhub_user_data_dir": self.jupyterhub_user_data_dir,
                    "wps_outputs_dir": self.wpsoutputs_dir}}})

        data = {
            "event": "created",
            "user_name": self.test_username,
            "callback_url": self.callback_url
        }
        resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
        utils.check_response_basic_info(resp, 200, expected_method="POST")
        assert self.user_workspace_dir.exists()
        assert os.path.islink(user_symlink)
        assert os.readlink(user_symlink) == os.path.join(self.jupyterhub_user_data_dir, self.test_username)
        utils.check_path_permissions(self.user_workspace_dir, 0o755)

        # Creating a user if its directory already exists should not trigger any errors.
        # The symlink should be recreated if it is missing.
        os.remove(user_symlink)

        resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
        utils.check_response_basic_info(resp, 200, expected_method="POST")
        assert self.user_workspace_dir.exists()
        utils.check_path_permissions(self.user_workspace_dir, 0o755)
        assert os.path.islink(user_symlink)
        assert os.readlink(user_symlink) == os.path.join(self.jupyterhub_user_data_dir, self.test_username)

        # If the directory already exists, it should correct the directory to have the right permissions.
        os.chmod(self.user_workspace_dir, 0o777)
        utils.check_path_permissions(self.user_workspace_dir, 0o777)

        resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
        utils.check_response_basic_info(resp, 200, expected_method="POST")
        assert self.user_workspace_dir.exists()
        utils.check_path_permissions(self.user_workspace_dir, 0o755)

        # If the symlink path already exists, but is a normal directory instead of a symlink,
        # an exception should occur.
        os.remove(user_symlink)
        os.mkdir(user_symlink)

        resp = utils.test_request(app, "POST", "/webhooks/users", json=data, expect_errors=True)
        utils.check_response_basic_info(resp, 500, expected_method="POST")
        assert "Failed to create symlinked directory" in resp.json_body["exception"]
        # The callback url should have been called if an exception occurred during the handler's operations.
        mock_head_request.assert_called_with(self.callback_url, verify=True, timeout=5)

        # If the symlink path already exists, but points to the wrong src directory, the symlink should be updated.
        os.rmdir(user_symlink)
        os.symlink("/wrong_source_dir", user_symlink, target_is_directory=True)

        resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
        utils.check_response_basic_info(resp, 200, expected_method="POST")
        assert os.path.islink(user_symlink)
        assert os.readlink(user_symlink) == os.path.join(self.jupyterhub_user_data_dir, self.test_username)

        data = {
            "event": "deleted",
            "user_name": self.test_username
        }
        resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
        utils.check_response_basic_info(resp, 200, expected_method="POST")
        assert not self.user_workspace_dir.exists()

        # Deleting a user if its directory does not exists should not trigger any errors.
        resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
        utils.check_response_basic_info(resp, 200, expected_method="POST")
        assert not self.user_workspace_dir.exists()

    @patch("cowbird.api.webhooks.views.requests.head")
    def test_create_user_missing_workspace_dir(self, mock_head_request):
        """
        Tests creating a user directory with a missing workspace directory.
        """
        workspace_dir = "/missing_dir"
        app = self.get_test_app({
            "handlers": {
                "FileSystem": {
                    "active": True,
                    "workspace_dir": workspace_dir,
                    "jupyterhub_user_data_dir": self.jupyterhub_user_data_dir,
                    "wps_outputs_dir": "/wpsoutputs"}}})
        data = {
            "event": "created",
            "user_name": self.test_username,
            "callback_url": self.callback_url
        }
        resp = utils.test_request(app, "POST", "/webhooks/users", json=data, expect_errors=True)
        utils.check_response_basic_info(resp, 500, expected_method="POST")
        assert not (Path(workspace_dir) / self.test_username).exists()
        assert "No such file or directory" in resp.json_body["exception"]

        # The callback url should have been called if an exception occurred during the handler's operations.
        mock_head_request.assert_called_with(self.callback_url, verify=True, timeout=5)

    def test_user_wps_output_created(self):
        """
        Tests creating a wps output for a user.
        """
        load_dotenv(CURR_DIR / "../docker/.env.example")
        self.get_test_app({
                "handlers": {
                    "Magpie": {
                        "active": True,
                        "url": os.getenv("COWBIRD_TEST_MAGPIE_URL"),
                        "admin_user": os.getenv("MAGPIE_ADMIN_USER"),
                        "admin_password": os.getenv("MAGPIE_ADMIN_PASSWORD")},
                    "FileSystem": {
                        "active": True,
                        "workspace_dir": self.workspace_dir,
                        "jupyterhub_user_data_dir": self.jupyterhub_user_data_dir,
                        "wps_outputs_dir": self.wpsoutputs_dir}}})

        # Reset test user
        magpie_test_user = "test_user"
        magpie_handler = HandlerFactory().get_handler("Magpie")
        test_magpie.delete_user(magpie_handler, magpie_test_user)
        user_id = test_magpie.create_user(magpie_handler, magpie_test_user,
                                          "test@test.com", "qwertyqwerty", "users")
        job_id = 1

        # Create a test wps output file
        # TODO: make case for directory, and files
        output_subpath = f"{job_id}/test_output.txt"
        output_file = os.path.join(self.wpsoutputs_dir,f"weaver/users/{user_id}/{output_subpath}")
        os.makedirs(os.path.dirname(output_file))
        open(output_file, mode="w").close()

        filesystem_handler = HandlerFactory().get_handler("FileSystem")
        # Error expected if the user workspace does not exist
        with pytest.raises(FileNotFoundError):
            filesystem_handler.on_created(output_file)

        # Create the user workspace
        filesystem_handler.user_created(magpie_test_user)
        filesystem_handler.on_created(output_file)

        hardlink_path = os.path.join(filesystem_handler._get_user_wps_outputs_user_dir(magpie_test_user),
                                     output_subpath)
        assert os.stat(hardlink_path).st_nlink == 2

        # Add test if dir already exists
        # Add test if the hardlink already exists (same whatever if the files is the right hardlink or unrelated)

    def test_public_wps_output_created(self):
        """
        Tests creating a public wps output file.
        """
        self.get_test_app({
            "handlers": {
                "FileSystem": {
                    "active": True,
                    "workspace_dir": self.workspace_dir,
                    "jupyterhub_user_data_dir": self.jupyterhub_user_data_dir,
                    "wps_outputs_dir": self.wpsoutputs_dir}}})

        # Create a test wps output file
        output_subpath = f"weaver/test_output.txt"
        output_file = os.path.join(self.wpsoutputs_dir, output_subpath)
        os.makedirs(os.path.dirname(output_file))
        open(output_file, mode="w").close()

        filesystem_handler = HandlerFactory().get_handler("FileSystem")
        filesystem_handler.on_created(output_file)

        hardlink_path = os.path.join(filesystem_handler._get_wps_outputs_public_dir(), output_subpath)
        assert os.stat(hardlink_path).st_nlink == 2

        # A create event should still work if the target directory already exists
        os.remove(hardlink_path)
        filesystem_handler.on_created(output_file)
        assert os.stat(hardlink_path).st_nlink == 2

        # A create event should replace a hardlink path with the new file if the target path already exists
        os.remove(hardlink_path)
        open(hardlink_path, mode="w").close()
        original_ctime = Path(output_file).stat().st_ctime
        sleep(1)
        filesystem_handler.on_created(output_file)
        new_ctime = Path(output_file).stat().st_ctime
        assert os.stat(hardlink_path).st_nlink == 2
        assert original_ctime != new_ctime

        # A create event on a folder should not be processed (no corresponding target folder created)
        target_weaver_dir = os.path.join(filesystem_handler._get_wps_outputs_public_dir(), "weaver")
        shutil.rmtree(target_weaver_dir)
        filesystem_handler.on_created(os.path.join(self.wpsoutputs_dir, "weaver"))
        assert not os.path.exists(target_weaver_dir)

    def test_public_wps_output_deleted(self):
        """
        Tests deleting a public wps output path.
        """
        self.get_test_app({
            "handlers": {
                "FileSystem": {
                    "active": True,
                    "workspace_dir": self.workspace_dir,
                    "jupyterhub_user_data_dir": self.jupyterhub_user_data_dir,
                    "wps_outputs_dir": self.wpsoutputs_dir}}})

        filesystem_handler = HandlerFactory().get_handler("FileSystem")

        output_subpath = f"weaver/test_output.txt"
        output_file_path = os.path.join(self.wpsoutputs_dir, output_subpath)

        # Create a file at the hardlink location
        hardlink_path = os.path.join(filesystem_handler._get_wps_outputs_public_dir(), output_subpath)
        os.makedirs(os.path.dirname(hardlink_path))
        open(hardlink_path, mode="w").close()

        with self.assertLogs('cowbird.handlers.impl.filesystem', level=logging.DEBUG) as log_capture:
            filesystem_handler.on_deleted(output_file_path)
            assert not os.path.exists(hardlink_path)
            assert len(log_capture.records) == 0

            # Should not fail if hardlink does not exist, but should display log message instead
            filesystem_handler.on_deleted(output_file_path)
            assert not os.path.exists(hardlink_path)
            assert len(log_capture.records) == 1

        # Test folder paths, the removal of a source folder should also remove the linked folder.
        weaver_linked_dir = os.path.join(filesystem_handler._get_wps_outputs_public_dir(), "weaver")
        assert os.path.exists(weaver_linked_dir)
        filesystem_handler.on_deleted(os.path.join(self.wpsoutputs_dir, "weaver"))
        assert not os.path.exists(weaver_linked_dir)

    def test_resync(self):
        """
        Tests resync operation for the handler.
        """
        app = self.get_test_app({
            "handlers": {
                "FileSystem": {
                    "active": True,
                    "workspace_dir": self.workspace_dir,
                    "jupyterhub_user_data_dir": self.jupyterhub_user_data_dir,
                    "wps_outputs_dir": self.wpsoutputs_dir}}})

        filesystem_handler = HandlerFactory().get_handler("FileSystem")

        # Create a file in a subfolder of the linked folder that should be removed by the resync
        old_nested_file = os.path.join(filesystem_handler._get_wps_outputs_public_dir(), "old_dir/old_file.txt")
        os.makedirs(os.path.dirname(old_nested_file))
        open(old_nested_file, mode="w").close()

        # Create a file at the root of the linked folder that should be removed by the resync
        old_root_file = os.path.join(filesystem_handler._get_wps_outputs_public_dir(), "old_root_file.txt")
        open(old_root_file, mode="w").close()

        # Create an empty subfolder in the linked folder that should be removed by the resync
        old_subdir = os.path.join(filesystem_handler._get_wps_outputs_public_dir(), "empty_subdir")
        os.mkdir(old_subdir)

        # Create a new test wps output file
        output_subpath = f"weaver/test_output.txt"
        output_file = os.path.join(self.wpsoutputs_dir, output_subpath)
        os.makedirs(os.path.dirname(output_file))
        open(output_file, mode="w").close()
        hardlink_path = os.path.join(filesystem_handler._get_wps_outputs_public_dir(), output_subpath)

        # Create a new empty dir (should not appear in the resynced wpsoutputs since only files are processed)
        new_dir = os.path.join(self.wpsoutputs_dir, "new_dir")
        os.mkdir(new_dir)
        new_dir_linked_path = os.path.join(filesystem_handler._get_wps_outputs_public_dir(), "new_dir")

        # Check that old files exist before applying the resync
        assert not os.path.exists(hardlink_path)
        assert os.path.exists(old_nested_file)
        assert os.path.exists(old_root_file)
        assert os.path.exists(old_subdir)

        resp = utils.test_request(app, "PUT", "/handlers/FileSystem/resync")

        # Check that new hardlinks are generated and old files are removed
        assert resp.status_code == 200
        assert os.stat(hardlink_path).st_nlink == 2
        assert not os.path.exists(new_dir_linked_path)
        assert not os.path.exists(old_nested_file)
        assert not os.path.exists(old_root_file)
        assert not os.path.exists(old_subdir)

    def test_resync_no_src_wpsoutputs(self):
        """
        Tests the resync operation when the source wpsoutputs folder does not exist.
        """
        app = self.get_test_app({
            "handlers": {
                "FileSystem": {
                    "active": True,
                    "workspace_dir": self.workspace_dir,
                    "jupyterhub_user_data_dir": self.jupyterhub_user_data_dir,
                    "wps_outputs_dir": "/missing_dir"}}})

        filesystem_handler = HandlerFactory().get_handler("FileSystem")

        # Create a file in a subfolder of the linked folder that should normally be removed by the resync
        old_nested_file = os.path.join(filesystem_handler._get_wps_outputs_public_dir(), "old_dir/old_file.txt")
        os.makedirs(os.path.dirname(old_nested_file))
        open(old_nested_file, mode="w").close()

        # Applying the resync should not crash even if the source wpsoutputs folder doesn't exist
        resp = utils.test_request(app, "PUT", "/handlers/FileSystem/resync")
        assert resp.status_code == 200

        # Check that previous file still exists, since resyncing was skipped because of the missing source folder
        assert os.path.exists(old_nested_file)
