import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pytest
import yaml

from tests import utils


@pytest.mark.filesystem
class TestFileSystem(unittest.TestCase):
    """
    Test FileSystem operations.
    """

    def setUp(self):
        self.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)  # pylint: disable=R1732
        self.test_username = "test_username"

    def tearDown(self):
        utils.clear_handlers_instances()
        os.unlink(self.cfg_file.name)

    def test_manage_user_workspace(self):
        """
        Tests creating and deleting a user workspace.
        """
        with tempfile.TemporaryDirectory() as workspace_dir:
            with self.cfg_file as f:
                f.write(yaml.safe_dump({"handlers":
                                        {"FileSystem": {"active": True, "workspace_dir": workspace_dir}}}))
            app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
            data = {
                "event": "created",
                "user_name": self.test_username,
                "callback_url": "callback_url"
            }
            resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            assert (Path(workspace_dir) / self.test_username).exists()

            # Creating a user if its directory already exists should not trigger any errors.
            resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            assert (Path(workspace_dir) / self.test_username).exists()

            data = {
                "event": "deleted",
                "user_name": self.test_username
            }
            resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            assert not (Path(workspace_dir) / self.test_username).exists()

            # Deleting a user if its directory does not exists should not trigger any errors.
            resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            assert not (Path(workspace_dir) / self.test_username).exists()

    @patch('cowbird.api.webhooks.views.requests.head')
    def test_create_user_missing_workspace_dir(self, mock_head_request):
        """
        Tests creating a user directory with a missing workspace directory.
        """
        workspace_dir = "/missing_dir"
        with self.cfg_file as f:
            f.write(yaml.safe_dump({"handlers":
                                    {"FileSystem": {"active": True, "workspace_dir": workspace_dir}}}))
        app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        callback_url = "callback_url"
        data = {
            "event": "created",
            "user_name": self.test_username,
            "callback_url": callback_url
        }
        resp = utils.test_request(app, "POST", "/webhooks/users", json=data, expect_errors=True)
        utils.check_response_basic_info(resp, 500, expected_method="POST")
        assert not (Path(workspace_dir) / self.test_username).exists()
        # The callback url should have been called if an exception occurred during the handler's operations.
        mock_head_request.assert_called_with(callback_url, verify=True, timeout=5)
