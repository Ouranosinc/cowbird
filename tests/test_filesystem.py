import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from cowbird.handlers.impl.filesystem import NOTEBOOKS_DIR_NAME
from tests import utils


@pytest.mark.filesystem
class TestFileSystem(unittest.TestCase):
    """
    Test FileSystem operations.
    """

    def setUp(self):
        self.test_username = "test_username"
        self.callback_url = "callback_url"
        self.jupyterhub_user_data_dir = "/jupyterhub_user_data"
        utils.clear_handlers_instances()

    def tearDown(self):
        utils.clear_handlers_instances()

    @patch("cowbird.api.webhooks.views.requests.head")
    def test_manage_user_workspace(self, mock_head_request):
        """
        Tests creating and deleting a user workspace.
        """
        with tempfile.TemporaryDirectory() as workspace_dir, \
                tempfile.NamedTemporaryFile(mode="w", suffix=".cfg") as cfg_file:
            user_workspace_dir = Path(workspace_dir) / self.test_username
            user_symlink = user_workspace_dir / NOTEBOOKS_DIR_NAME

            cfg_file.write(yaml.safe_dump({
                "handlers": {
                    "FileSystem": {
                        "active": True,
                        "workspace_dir": workspace_dir,
                        "jupyterhub_user_data_dir": self.jupyterhub_user_data_dir}}}))
            cfg_file.flush()
            app = utils.get_test_app(settings={"cowbird.config_path": cfg_file.name})
            data = {
                "event": "created",
                "user_name": self.test_username,
                "callback_url": self.callback_url
            }
            resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            assert user_workspace_dir.exists()
            assert os.path.islink(user_symlink)
            assert os.readlink(user_symlink) == os.path.join(self.jupyterhub_user_data_dir, self.test_username)
            utils.check_path_permissions(user_workspace_dir, 0o755)

            # Creating a user if its directory already exists should not trigger any errors.
            # The symlink should be recreated if it is missing.
            os.remove(user_symlink)

            resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            assert user_workspace_dir.exists()
            utils.check_path_permissions(user_workspace_dir, 0o755)
            assert os.path.islink(user_symlink)
            assert os.readlink(user_symlink) == os.path.join(self.jupyterhub_user_data_dir, self.test_username)

            # If the directory already exists, it should correct the directory to have the right permissions.
            os.chmod(user_workspace_dir, 0o777)
            utils.check_path_permissions(user_workspace_dir, 0o777)

            resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            assert user_workspace_dir.exists()
            utils.check_path_permissions(user_workspace_dir, 0o755)

            # If the symlink path already exists, but is a normal directory instead of a symlink,
            # an exception should occur.
            os.remove(user_symlink)
            os.mkdir(user_symlink)

            resp = utils.test_request(app, "POST", "/webhooks/users", json=data, expect_errors=True)
            utils.check_response_basic_info(resp, 500, expected_method="POST")
            assert "Failed to create symlinked jupyterhub directory" in resp.json_body["exception"]
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
            assert not user_workspace_dir.exists()

            # Deleting a user if its directory does not exists should not trigger any errors.
            resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            assert not user_workspace_dir.exists()

    @patch("cowbird.api.webhooks.views.requests.head")
    def test_create_user_missing_workspace_dir(self, mock_head_request):
        """
        Tests creating a user directory with a missing workspace directory.
        """
        workspace_dir = "/missing_dir"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg") as cfg_file:
            cfg_file.write(yaml.safe_dump({
                "handlers": {
                    "FileSystem": {
                        "active": True,
                        "workspace_dir": workspace_dir,
                        "jupyterhub_user_data_dir": self.jupyterhub_user_data_dir}}}))
            cfg_file.flush()
            app = utils.get_test_app(settings={"cowbird.config_path": cfg_file.name})
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
