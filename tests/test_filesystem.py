import logging
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from dotenv import load_dotenv
from magpie.models import Permission, Route
from magpie.permissions import Access, Scope
from magpie.services import ServiceAPI
from webtest.app import TestApp

from cowbird.handlers import HandlerFactory
from cowbird.handlers.impl.filesystem import NOTEBOOKS_DIR_NAME, SECURE_DATA_PROXY_NAME
from cowbird.typedefs import JSON
from tests import test_magpie, utils

CURR_DIR = Path(__file__).resolve().parent


@pytest.mark.filesystem
class TestFileSystem(unittest.TestCase):
    """
    Test FileSystem parent class, containing some utility functions and common setup/teardown operations.
    """

    @classmethod
    def setUpClass(cls):
        cls.jupyterhub_user_data_dir = "/jupyterhub_user_data"
        cls.test_username = "test_user"
        cls.callback_url = "callback_url"

        # Mock monitoring to disable monitoring events and to trigger file events manually instead during tests.
        cls.patcher = patch("cowbird.monitoring.monitoring.Monitoring.register")
        cls.mock_register = cls.patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    def setUp(self):
        self.test_directory = tempfile.TemporaryDirectory()  # pylint: disable=R1732,consider-using-with
        self.workspace_dir = os.path.join(self.test_directory.name, "user_workspaces")
        self.wpsoutputs_dir = os.path.join(self.test_directory.name, "wpsoutputs")
        os.mkdir(self.workspace_dir)
        os.mkdir(self.wpsoutputs_dir)

        self.user_workspace_dir = Path(self.workspace_dir) / self.test_username

    def tearDown(self):
        utils.clear_handlers_instances()
        self.test_directory.cleanup()

    def get_test_app(self, cfg_data: JSON) -> TestApp:
        cfg_file = os.path.join(self.test_directory.name, "config.yml")
        with open(cfg_file, "w", encoding="utf-8") as f:
            f.write(yaml.safe_dump(cfg_data))
        utils.clear_handlers_instances()
        app = utils.get_test_app(settings={"cowbird.config_path": cfg_file})
        return app

    @staticmethod
    def check_created_test_cases(output_path, hardlink_path):
        """
        Runs multiple test cases for the creation of hardlinks, which are the same for public and user files.
        """
        # Make sure the hardlink doesn't already exist for the test cases
        Path(hardlink_path).unlink(missing_ok=True)

        # A create event on the file should create a corresponding hardlink
        filesystem_handler = HandlerFactory().get_handler("FileSystem")
        filesystem_handler.on_created(output_path)
        assert os.stat(hardlink_path).st_nlink == 2

        # A create event should still work if the target directory already exists
        os.remove(hardlink_path)
        filesystem_handler.on_created(output_path)
        assert os.stat(hardlink_path).st_nlink == 2

        # A create event should replace a hardlink path with the new file if the target path already exists
        os.remove(hardlink_path)
        with open(hardlink_path, mode="w", encoding="utf-8"):
            pass
        original_hardlink_ino = Path(hardlink_path).stat().st_ino
        filesystem_handler.on_created(output_path)
        new_hardlink_ino = Path(hardlink_path).stat().st_ino
        assert original_hardlink_ino != new_hardlink_ino
        assert Path(output_path).stat().st_ino == new_hardlink_ino
        assert os.stat(hardlink_path).st_nlink == 2


@pytest.mark.filesystem
class TestFileSystemBasic(TestFileSystem):
    """
    Test FileSystem generic operations.
    """
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
        bird_name = "weaver"
        output_subpath = f"{bird_name}/test_output.txt"
        output_file = os.path.join(self.wpsoutputs_dir, output_subpath)
        os.makedirs(os.path.dirname(output_file))
        with open(output_file, mode="w", encoding="utf-8"):
            pass

        filesystem_handler = HandlerFactory().get_handler("FileSystem")
        hardlink_path = os.path.join(filesystem_handler.get_wps_outputs_public_dir(), output_subpath)

        TestFileSystem.check_created_test_cases(output_file, hardlink_path)

        # A create event on a folder should not be processed (no corresponding target folder created)
        target_dir = os.path.join(filesystem_handler.get_wps_outputs_public_dir(), bird_name)
        shutil.rmtree(target_dir)
        filesystem_handler.on_created(os.path.join(self.wpsoutputs_dir, bird_name))
        assert not os.path.exists(target_dir)

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

        output_subpath = "weaver/test_output.txt"
        output_file_path = os.path.join(self.wpsoutputs_dir, output_subpath)

        # Create a file at the hardlink location
        hardlink_path = os.path.join(filesystem_handler.get_wps_outputs_public_dir(), output_subpath)
        os.makedirs(os.path.dirname(hardlink_path))
        with open(hardlink_path, mode="w", encoding="utf-8"):
            pass

        with self.assertLogs("cowbird.handlers.impl.filesystem", level=logging.DEBUG) as log_capture:
            filesystem_handler.on_deleted(output_file_path)
            assert not os.path.exists(hardlink_path)
            assert len([r for r in log_capture.records if r.levelno == logging.DEBUG]) == 0

            # Should not fail if hardlink does not exist, but should display log message instead
            filesystem_handler.on_deleted(output_file_path)
            assert not os.path.exists(hardlink_path)
            assert len([r for r in log_capture.records if r.levelno == logging.DEBUG]) == 1

        # Test folder paths, the removal of a source folder should also remove the linked folder.
        weaver_linked_dir = os.path.join(filesystem_handler.get_wps_outputs_public_dir(), "weaver")
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
        old_nested_file = os.path.join(filesystem_handler.get_wps_outputs_public_dir(), "old_dir/old_file.txt")
        os.makedirs(os.path.dirname(old_nested_file))
        with open(old_nested_file, mode="w", encoding="utf-8"):
            pass

        # Create a file at the root of the linked folder that should be removed by the resync
        old_root_file = os.path.join(filesystem_handler.get_wps_outputs_public_dir(), "old_root_file.txt")
        with open(old_root_file, mode="w", encoding="utf-8"):
            pass

        # Create an empty subfolder in the linked folder that should be removed by the resync
        old_subdir = os.path.join(filesystem_handler.get_wps_outputs_public_dir(), "empty_subdir")
        os.mkdir(old_subdir)

        # Create a new test wps output file
        output_subpath = "weaver/test_output.txt"
        output_file = os.path.join(self.wpsoutputs_dir, output_subpath)
        os.makedirs(os.path.dirname(output_file))
        with open(output_file, mode="w", encoding="utf-8"):
            pass
        hardlink_path = os.path.join(filesystem_handler.get_wps_outputs_public_dir(), output_subpath)

        # Create a new empty dir (should not appear in the resynced wpsoutputs since only files are processed)
        new_dir = os.path.join(self.wpsoutputs_dir, "new_dir")
        os.mkdir(new_dir)
        new_dir_linked_path = os.path.join(filesystem_handler.get_wps_outputs_public_dir(), "new_dir")

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
                    "wps_outputs_dir": self.wpsoutputs_dir}}})

        filesystem_handler = HandlerFactory().get_handler("FileSystem")

        shutil.rmtree(self.wpsoutputs_dir)

        # Create a file in a subfolder of the linked folder that should normally be removed by the resync
        old_nested_file = os.path.join(filesystem_handler.get_wps_outputs_public_dir(), "old_dir/old_file.txt")
        os.makedirs(os.path.dirname(old_nested_file))
        with open(old_nested_file, mode="w", encoding="utf-8"):
            pass

        # Applying the resync should not crash even if the source wpsoutputs folder doesn't exist
        resp = utils.test_request(app, "PUT", "/handlers/FileSystem/resync")
        assert resp.status_code == 200

        # Check that previous file still exists, since resyncing was skipped because of the missing source folder
        assert os.path.exists(old_nested_file)


@pytest.mark.filesystem
class TestFileSystemWpsOutputsUser(TestFileSystem):
    """
    FileSystem tests specific to the user wps outputs data.
    """
    def setUp(self):
        super().setUp()
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
        magpie_handler = HandlerFactory().get_handler("Magpie")
        test_magpie.delete_user(magpie_handler, self.test_username)
        self.user_id = test_magpie.create_user(magpie_handler, self.test_username,
                                               "test@test.com", "qwertyqwerty", "users")

        self.job_id = 1
        self.bird_name = "weaver"
        self.output_subpath = f"{self.job_id}/test_output.txt"
        self.output_file = os.path.join(self.wpsoutputs_dir,
                                        f"{self.bird_name}/users/{self.user_id}/{self.output_subpath}")
        filesystem_handler = HandlerFactory().get_handler("FileSystem")
        self.wps_outputs_user_dir = filesystem_handler.get_wps_outputs_user_dir(self.test_username)
        # Hardlink for user files doesn't use the full subpath, but removes the redundant `users` and `{user_id}` parts.
        self.hardlink_path = os.path.join(self.wps_outputs_user_dir, f"{self.bird_name}/{self.output_subpath}")

        # Create the test wps output file
        os.makedirs(os.path.dirname(self.output_file))
        with open(self.output_file, mode="w", encoding="utf-8"):
            pass

        self.secure_data_proxy_name = SECURE_DATA_PROXY_NAME
        # Delete the service if it already exists
        test_magpie.delete_service(magpie_handler, self.secure_data_proxy_name)

    def create_secure_data_proxy_service(self):
        """
        Generates a new secure-data-proxy service in Magpie app.
        """
        # Create service
        data = {
            "service_name": self.secure_data_proxy_name,
            "service_type": ServiceAPI.service_type,
            "service_sync_type": ServiceAPI.service_type,
            "service_url": f"http://localhost:9000/{self.secure_data_proxy_name}",
            "configuration": {}
        }
        return test_magpie.create_service(HandlerFactory().get_handler("Magpie"), data)

    def test_user_wps_output_created(self):
        """
        Tests creating wps outputs for a user.
        """
        filesystem_handler = HandlerFactory().get_handler("FileSystem")

        # Error expected if the user workspace does not exist
        with pytest.raises(FileNotFoundError):
            filesystem_handler.on_created(self.output_file)

        # Create the user workspace
        filesystem_handler.user_created(self.test_username)

        TestFileSystem.check_created_test_cases(self.output_file, self.hardlink_path)

        # A create event on a folder should not be processed (no corresponding target folder created)
        src_dir = os.path.join(self.wpsoutputs_dir, f"{self.bird_name}/users/{self.user_id}/{self.job_id}")
        target_dir = os.path.join(self.wps_outputs_user_dir, f"{self.bird_name}/{self.job_id}")
        shutil.rmtree(target_dir)
        filesystem_handler.on_created(src_dir)
        assert not os.path.exists(target_dir)

    def test_user_wps_output_created_secure_data_proxy(self):
        """
        Tests creating wps outputs for a user when Magpie uses a secure-data-proxy service to manage access permissions
        to the wps output data.
        """
        filesystem_handler = HandlerFactory().get_handler("FileSystem")
        magpie_handler = HandlerFactory().get_handler("Magpie")
        filesystem_handler.user_created(self.test_username)
        svc_id = self.create_secure_data_proxy_service()

        # Note that the following test cases are made to be executed in a specific order and are not interchangeable.
        test_cases = [{
            # If secure-data-proxy service exists but no route is defined for wpsoutputs,
            # assume access is not allowed and check if no hardlink is created.
            "routes_to_create": [],
            "permissions_cases": [("", "", False, 0o660)]
        }, {
            # Permission applied only on a parent resource
            # If the route is only defined on a parent resource and no route are defined for the actual file,
            # assume access is the same as the access of the parent, and hardlink should be created accordingly.
            "routes_to_create": ["wpsoutputs"],
            "permissions_cases": [(Permission.READ.value, Access.DENY.value, False, 0o660),
                                  (Permission.READ.value, Access.ALLOW.value, True, 0o664),
                                  (Permission.WRITE.value, Access.ALLOW.value, True, 0o666),
                                  (Permission.WRITE.value, Access.DENY.value, True, 0o664)]
        }, {
            # Permission applied on the actual resource - Test access with an exact route match
            # Create the rest of the route to get a route that match the actual full path of the resource
            "routes_to_create": re.sub(rf"^{self.wpsoutputs_dir}", "", self.output_file).strip("/").split("/"),
            "permissions_cases": [(Permission.READ.value, Access.DENY.value, False, 0o660),
                                  (Permission.READ.value, Access.ALLOW.value, True, 0o664),
                                  (Permission.WRITE.value, Access.ALLOW.value, True, 0o666),
                                  (Permission.WRITE.value, Access.DENY.value, True, 0o664)]}]
        # Resource id of the last existing route resource found from the path of the test file
        last_res_id = svc_id

        for test_case in test_cases:
            # Create routes found in list
            for route in test_case["routes_to_create"]:
                last_res_id = magpie_handler.create_resource(route, Route.resource_type_name, last_res_id)
            for perm_name, perm_access, expecting_created_file, expected_file_perms in test_case["permissions_cases"]:
                # Reset hardlink file for each test
                shutil.rmtree(self.wps_outputs_user_dir, ignore_errors=True)

                # Create permission if required
                if perm_name and perm_access:
                    magpie_handler.create_permission_by_user_and_res_id(
                        user_name=self.test_username,
                        res_id=last_res_id,
                        perm_name=perm_name,
                        perm_access=perm_access,
                        perm_scope=Scope.MATCH.value)

                # Check if file is created according to permissions
                filesystem_handler.on_created(self.output_file)
                assert expecting_created_file == os.path.exists(self.hardlink_path)
                utils.check_path_permissions(self.output_file, expected_file_perms)

    def test_user_wps_output_deleted(self):
        """
        Tests deleting wps outputs for a user.
        """
        filesystem_handler = HandlerFactory().get_handler("FileSystem")

        # Create the user workspace
        filesystem_handler.user_created(self.test_username)

        # Basic test cases for deleting user wps outputs. More extensive delete test cases are done in the public tests.
        # Test deleting a user file.
        filesystem_handler.on_created(self.output_file)
        assert os.path.exists(self.hardlink_path)
        filesystem_handler.on_deleted(self.output_file)
        assert not os.path.exists(self.hardlink_path)

        # Test deleting a user directory
        src_dir = os.path.join(self.wpsoutputs_dir, f"{self.bird_name}/users/{self.user_id}/{self.job_id}")
        target_dir = os.path.join(self.wps_outputs_user_dir, f"{self.bird_name}/{self.job_id}")
        assert os.path.exists(target_dir)
        filesystem_handler.on_deleted(src_dir)
        assert not os.path.exists(target_dir)
