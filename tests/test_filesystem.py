import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from dotenv import load_dotenv

from cowbird.handlers import HandlerFactory
from cowbird.handlers.impl.filesystem import NOTEBOOKS_DIR_NAME, USER_WPSOUTPUTS_PUBLIC_DIR_NAME
from tests import test_magpie, utils

CURR_DIR = Path(__file__).resolve().parent


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
                tempfile.TemporaryDirectory() as wpsoutputs_dir, \
                tempfile.NamedTemporaryFile(mode="w", suffix=".cfg") as cfg_file:
            user_workspace_dir = Path(workspace_dir) / self.test_username
            user_symlink = user_workspace_dir / NOTEBOOKS_DIR_NAME
            public_wpsoutputs_symlink = user_workspace_dir / USER_WPSOUTPUTS_PUBLIC_DIR_NAME

            cfg_file.write(yaml.safe_dump({
                "handlers": {
                    "FileSystem": {
                        "active": True,
                        "workspace_dir": workspace_dir,
                        "jupyterhub_user_data_dir": self.jupyterhub_user_data_dir,
                        "wps_outputs_dir": wpsoutputs_dir}}}))
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
            assert os.path.islink(public_wpsoutputs_symlink)
            assert os.readlink(public_wpsoutputs_symlink) == wpsoutputs_dir

            # Creating a user if its directory already exists should not trigger any errors.
            # The symlink should be recreated if it is missing.
            os.remove(user_symlink)

            resp = utils.test_request(app, "POST", "/webhooks/users", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            assert user_workspace_dir.exists()
            utils.check_path_permissions(user_workspace_dir, 0o755)
            assert os.path.islink(user_symlink)
            assert os.readlink(user_symlink) == os.path.join(self.jupyterhub_user_data_dir, self.test_username)
            assert os.path.islink(public_wpsoutputs_symlink)
            assert os.readlink(public_wpsoutputs_symlink) == wpsoutputs_dir

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
                        "jupyterhub_user_data_dir": self.jupyterhub_user_data_dir,
                        "wps_outputs_dir": "/wpsoutputs"}}}))
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

    def test_user_wps_output_created(self):
        """
        Tests creating a wps output for a user.
        """
        with tempfile.TemporaryDirectory() as workspace_dir, \
                tempfile.NamedTemporaryFile(mode="w", suffix=".cfg") as cfg_file, \
                tempfile.TemporaryDirectory() as wpsoutputs_dir:
            user_workspace_dir = Path(workspace_dir) / self.test_username

            load_dotenv(CURR_DIR / "../docker/.env.example")
            cfg_file.write(yaml.safe_dump({
                "handlers": {
                    "Magpie": {
                        "active": True,
                        "url": os.getenv("COWBIRD_TEST_MAGPIE_URL"),
                        "admin_user": os.getenv("MAGPIE_ADMIN_USER"),
                        "admin_password": os.getenv("MAGPIE_ADMIN_PASSWORD")},
                    "FileSystem": {
                        "active": True,
                        "workspace_dir": workspace_dir,
                        "jupyterhub_user_data_dir": self.jupyterhub_user_data_dir,
                        "wps_outputs_dir": wpsoutputs_dir}}}))
            cfg_file.flush()
            app = utils.get_test_app(settings={"cowbird.config_path": cfg_file.name})

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
            output_file = os.path.join(wpsoutputs_dir,f"weaver/users/{user_id}/{output_subpath}")
            os.makedirs(os.path.dirname(output_file))
            open(output_file, mode="w").close()

            filesystem_handler = HandlerFactory().create_handler("FileSystem")
            # Error expected if the user workspace does not exist
            with pytest.raises(FileNotFoundError):
                filesystem_handler.on_created(output_file)

            # Create the user workspace
            filesystem_handler.user_created(magpie_test_user)
            filesystem_handler.on_created(output_file)

            hardlink_path = os.path.join(filesystem_handler._get_user_wps_outputs_dir(magpie_test_user), output_subpath)
            assert os.stat(hardlink_path).st_nlink == 2
