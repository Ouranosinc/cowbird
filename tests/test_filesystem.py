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

from cowbird.api.schemas import ValidOperations
from cowbird.handlers import HandlerFactory
from cowbird.handlers.impl.filesystem import NOTEBOOKS_DIR_NAME, SECURE_DATA_PROXY_NAME, USER_WPS_OUTPUTS_USER_DIR_NAME
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

        # Check that the hardlink's parent directory have the right permissions
        utils.check_path_permissions(os.path.dirname(hardlink_path), 0o775)

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
        load_dotenv(CURR_DIR / "../docker/.env.example")
        app = self.get_test_app({
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
        self.app = self.get_test_app({
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
        filesystem_handler = HandlerFactory().get_handler("FileSystem")
        magpie_handler = HandlerFactory().get_handler("Magpie")
        test_magpie.delete_user(magpie_handler, self.test_username)
        self.user_id = test_magpie.create_user(magpie_handler, self.test_username,
                                               "test@test.com", "qwertyqwerty", "users")
        filesystem_handler.user_created(self.test_username)

        self.job_id = 1
        self.bird_name = "weaver"
        self.output_filename = "test_output.txt"
        subpath = f"{self.job_id}/{self.output_filename}"
        self.output_file = os.path.join(self.wpsoutputs_dir,
                                        f"{self.bird_name}/users/{self.user_id}/{subpath}")
        self.wps_outputs_user_dir = filesystem_handler.get_wps_outputs_user_dir(self.test_username)
        self.hardlink_path = filesystem_handler.get_user_hardlink(src_path=self.output_file,
                                                                  bird_name=self.bird_name,
                                                                  user_name=self.test_username,
                                                                  subpath=subpath)

        # Create the test wps output file
        os.makedirs(os.path.dirname(self.output_file))
        with open(self.output_file, mode="w", encoding="utf-8"):
            pass
        os.chmod(self.output_file, 0o666)

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

    @staticmethod
    def check_path_perms_and_hardlink(src_path: str, hardlink_path: str, perms: int):
        """
        Checks if a path has the expected permissions, and if a hardlink exists, according to the `other` permissions.
        """
        utils.check_path_permissions(src_path, perms)
        if perms & 0o006:  # check if path has a read or write permission set for `other`
            assert os.path.exists(hardlink_path)
        else:
            assert not os.path.exists(hardlink_path)

    def test_user_wps_output_created(self):
        """
        Tests creating wps outputs for a user.
        """
        filesystem_handler = HandlerFactory().get_handler("FileSystem")

        # Error expected if the user workspace does not exist
        shutil.rmtree(filesystem_handler.get_user_workspace_dir(self.test_username))
        with pytest.raises(FileNotFoundError):
            filesystem_handler.on_created(self.output_file)

        # Create the user workspace
        filesystem_handler.user_created(self.test_username)

        TestFileSystem.check_created_test_cases(self.output_file, self.hardlink_path)

        # Check that the hardlink's parent directory has the right permissions
        utils.check_path_permissions(os.path.dirname(self.hardlink_path), 0o777)

        # A create event on a folder should not be processed (no corresponding target folder created)
        src_dir = os.path.join(self.wpsoutputs_dir, f"{self.bird_name}/users/{self.user_id}/{self.job_id}")
        target_dir = os.path.join(self.wps_outputs_user_dir, f"{self.bird_name}/{self.job_id}")
        shutil.rmtree(target_dir)
        filesystem_handler.on_created(src_dir)
        assert not os.path.exists(target_dir)

    def test_user_created(self):
        """
        Tests if creating a user generates the hardlinks to the pre-existing user wpsoutputs data.
        """
        filesystem_handler = HandlerFactory().get_handler("FileSystem")
        shutil.rmtree(filesystem_handler.get_user_workspace_dir(self.test_username))

        # Simulate a user_created event and check that the expected hardlink is generated.
        filesystem_handler.user_created(self.test_username)
        assert os.stat(self.hardlink_path).st_nlink == 2

    def test_user_wps_output_created_secure_data_proxy(self):
        """
        Tests creating wps outputs for a user when Magpie uses a secure-data-proxy service to manage access permissions
        to the wps output data.
        """
        filesystem_handler = HandlerFactory().get_handler("FileSystem")
        magpie_handler = HandlerFactory().get_handler("Magpie")
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

    def test_resync(self):
        """
        Tests resync operation on wpsoutputs user data.
        """

        test_dir = os.path.join(self.wps_outputs_user_dir, f"{self.bird_name}/{self.job_id}")

        # Create a file in a subfolder of the linked folder that should be removed by the resync
        old_nested_file = os.path.join(test_dir, "old_dir/old_file.txt")
        os.makedirs(os.path.dirname(old_nested_file))
        with open(old_nested_file, mode="w", encoding="utf-8"):
            pass

        # Create an empty subfolder in the linked folder that should be removed by the resync
        old_subdir = os.path.join(test_dir, "empty_subdir")
        os.mkdir(old_subdir)

        # Create a new empty dir (should not appear in the resynced wpsoutputs since only files are processed)
        new_dir = os.path.join(self.wpsoutputs_dir, f"{self.bird_name}/users/{self.user_id}/new_dir")
        os.mkdir(new_dir)
        new_dir_linked_path = os.path.join(self.wps_outputs_user_dir, f"{self.bird_name}/new_dir")

        # Check that old files exist before applying the resync
        assert not os.path.exists(self.hardlink_path)
        assert os.path.exists(old_nested_file)
        assert os.path.exists(old_subdir)

        resp = utils.test_request(self.app, "PUT", "/handlers/FileSystem/resync")

        # Check that new hardlinks are generated and old files are removed
        assert resp.status_code == 200
        assert os.stat(self.hardlink_path).st_nlink == 2
        assert not os.path.exists(new_dir_linked_path)
        assert not os.path.exists(old_nested_file)
        assert not os.path.exists(old_subdir)

    def test_permission_updates_user_data(self):
        """
        Tests updating permissions on data found directly in a specific user directory.
        """
        magpie_handler = HandlerFactory().get_handler("Magpie")
        # Create resources for the full route
        svc_id = self.create_secure_data_proxy_service()

        # Prepare test files
        subdir_test_file = self.output_file
        subdir_hardlink = self.hardlink_path
        root_test_filename = "other_file.txt"
        root_test_file = os.path.join(self.wpsoutputs_dir,
                                      f"{self.bird_name}/users/{self.user_id}/{root_test_filename}")
        root_hardlink = HandlerFactory().get_handler("FileSystem").get_user_hardlink(
            src_path=root_test_file, bird_name=self.bird_name, user_name=self.test_username, subpath=root_test_filename)
        with open(root_test_file, mode="w", encoding="utf-8"):
            pass
        for file in [root_test_file, subdir_test_file]:
            os.chmod(file, 0o660)

        # Prepare test routes
        user_dir_res_id = None
        routes = re.sub(rf"^{self.wpsoutputs_dir}", "wpsoutputs", self.output_file).strip("/")
        last_res_id = svc_id
        for route in routes.split("/"):
            last_res_id = magpie_handler.create_resource(route, Route.resource_type_name, last_res_id)
            if route == str(self.user_id):
                user_dir_res_id = last_res_id
        if not user_dir_res_id:
            raise ValueError("Missing resource id for the user directory, invalid test.")
        subdir_file_res_id = last_res_id
        magpie_handler.create_resource(root_test_filename, Route.resource_type_name, user_dir_res_id)

        data = {
            "event": ValidOperations.CreateOperation.value,
            "service_name": None,
            "service_type": ServiceAPI.service_type,
            "resource_id": user_dir_res_id,
            "resource_full_name": "test-full-name",
            "name": Permission.READ.value,
            "access": Access.ALLOW.value,
            "scope": Scope.MATCH.value,
            "user": self.test_username,
            "group": None
        }
        magpie_handler.create_permission_by_res_id(data["resource_id"], data["name"], data["access"],
                                                   data["scope"], data["user"])
        # Files should still have no permissions since dir permission is match-only.
        resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
        assert resp.status_code == 200
        self.check_path_perms_and_hardlink(root_test_file, root_hardlink, 0o660)
        self.check_path_perms_and_hardlink(subdir_test_file, subdir_hardlink, 0o660)

        # File permissions should be updated with the recursive permission on the parent directory.
        data["scope"] = Scope.RECURSIVE.value
        magpie_handler.create_permission_by_res_id(data["resource_id"], data["name"], data["access"],
                                                   data["scope"], data["user"])
        resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
        assert resp.status_code == 200
        self.check_path_perms_and_hardlink(root_test_file, root_hardlink, 0o664)
        self.check_path_perms_and_hardlink(subdir_test_file, subdir_hardlink, 0o664)

        # Permission applied directly to a file
        data["resource_id"] = subdir_file_res_id
        data["name"] = Permission.WRITE.value
        data["scope"] = Scope.MATCH.value
        magpie_handler.create_permission_by_res_id(data["resource_id"], data["name"], data["access"],
                                                   data["scope"], data["user"])
        resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
        assert resp.status_code == 200
        self.check_path_perms_and_hardlink(root_test_file, root_hardlink, 0o664)
        self.check_path_perms_and_hardlink(subdir_test_file, subdir_hardlink, 0o666)

        # Test deleting permission on a directory
        data["event"] = ValidOperations.DeleteOperation.value
        data["resource_id"] = user_dir_res_id
        data["name"] = Permission.READ.value
        magpie_handler.delete_permission_by_user_and_res_id(data["user"], data["resource_id"], data["name"])
        resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
        assert resp.status_code == 200
        self.check_path_perms_and_hardlink(root_test_file, root_hardlink, 0o660)
        self.check_path_perms_and_hardlink(subdir_test_file, subdir_hardlink, 0o662)

        # Test deleting permission on a file
        data["resource_id"] = subdir_file_res_id
        data["name"] = Permission.WRITE.value
        magpie_handler.delete_permission_by_user_and_res_id(data["user"], data["resource_id"], data["name"])
        resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
        assert resp.status_code == 200
        self.check_path_perms_and_hardlink(root_test_file, root_hardlink, 0o660)
        self.check_path_perms_and_hardlink(subdir_test_file, subdir_hardlink, 0o660)

    def test_permission_updates_wpsoutputs_data(self):
        """
        Tests updating permissions on data found outside of the user directories, including testing permissions on a
        user and on a group.
        """
        filesystem_handler = HandlerFactory().get_handler("FileSystem")
        magpie_handler = HandlerFactory().get_handler("Magpie")
        # Create resources for the full route
        svc_id = self.create_secure_data_proxy_service()

        # Create other user from a group different than the test group
        test_magpie.delete_group(magpie_handler, "others")
        test_magpie.create_group(magpie_handler, "others", "", True, "")
        ignored_username = "ignored-user"
        test_magpie.delete_user(magpie_handler, ignored_username)
        ignored_user_id = test_magpie.create_user(magpie_handler, ignored_username,
                                                  "ignored@test.com", "qwertyqwerty", "others")
        filesystem_handler.user_created(ignored_username)

        # Create other user from the same group as the original test user
        same_group_username = "same-group-user"
        test_magpie.delete_user(magpie_handler, same_group_username)
        same_group_user_id = test_magpie.create_user(magpie_handler, same_group_username,
                                                     "samegroup@test.com", "qwertyqwerty", "users")
        filesystem_handler.user_created(same_group_username)

        # Create other test files
        # Public files should be ignored by following test cases,
        # since public files are not concerned by perm change events.
        public_file = os.path.join(self.wpsoutputs_dir, "public_file.txt")
        public_subfile = os.path.join(self.wpsoutputs_dir, "public_dir/public_file.txt")

        # This file should be ignored by following test cases, being in a group different than the test group.
        ignored_filename = "ignored.txt"
        ignored_file = os.path.join(self.wpsoutputs_dir, f"{self.bird_name}/users/{ignored_user_id}/{ignored_filename}")
        ignored_hardlink = filesystem_handler.get_user_hardlink(
            src_path=ignored_file, bird_name=self.bird_name, user_name=ignored_username, subpath=ignored_filename)

        same_group_filename = "same_group.txt"
        same_group_file = os.path.join(self.wpsoutputs_dir,
                                       f"{self.bird_name}/users/{same_group_user_id}/{same_group_filename}")
        same_group_hardlink = filesystem_handler.get_user_hardlink(src_path=same_group_file,
                                                                   bird_name=self.bird_name,
                                                                   user_name=same_group_username,
                                                                   subpath=same_group_filename)

        for file in [self.output_file, public_file, public_subfile, ignored_file, same_group_file]:
            os.makedirs(os.path.dirname(file), exist_ok=True)
            with open(file, mode="w", encoding="utf-8"):
                pass
            os.chmod(file, 0o660)

        # Create resource
        res_id = magpie_handler.create_resource("wpsoutputs", Route.resource_type_name, svc_id)

        data = {
            "event": ValidOperations.CreateOperation.value,
            "service_name": None,
            "service_type": ServiceAPI.service_type,
            "resource_id": res_id,
            "resource_full_name": "test-full-name",
            "name": Permission.READ.value,
            "access": Access.ALLOW.value,
            "scope": Scope.RECURSIVE.value,
            "user": self.test_username,
            "group": None
        }
        magpie_handler.create_permission_by_res_id(data["resource_id"], data["name"], data["access"], data["scope"],
                                                   user_name=data["user"])
        # Check that perms was only updated for concerned user files
        resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
        assert resp.status_code == 200
        self.check_path_perms_and_hardlink(self.output_file, self.hardlink_path, 0o664)
        self.check_path_perms_and_hardlink(ignored_file, ignored_hardlink, 0o660)
        self.check_path_perms_and_hardlink(same_group_file, same_group_hardlink, 0o660)
        utils.check_path_permissions(public_file, 0o660)
        utils.check_path_permissions(public_subfile, 0o660)

        # Check that perms are updated for all the users of the concerned group
        data["user"] = None
        data["group"] = "users"
        data["name"] = Permission.WRITE.value
        magpie_handler.create_permission_by_res_id(data["resource_id"], data["name"], data["access"], data["scope"],
                                                   grp_name=data["group"])
        resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
        assert resp.status_code == 200
        self.check_path_perms_and_hardlink(self.output_file, self.hardlink_path, 0o666)
        self.check_path_perms_and_hardlink(ignored_file, ignored_hardlink, 0o660)
        self.check_path_perms_and_hardlink(same_group_file, same_group_hardlink, 0o662)
        utils.check_path_permissions(public_file, 0o660)
        utils.check_path_permissions(public_subfile, 0o660)

        # Add read-deny group permissions for next test cases
        data["name"] = Permission.READ.value
        data["access"] = Access.DENY.value
        magpie_handler.create_permission_by_res_id(data["resource_id"], data["name"], data["access"], data["scope"],
                                                   grp_name=data["group"])
        utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
        self.check_path_perms_and_hardlink(self.output_file, self.hardlink_path, 0o666)

        # Test deleting a specific user permission
        data["event"] = ValidOperations.DeleteOperation.value
        data["user"] = self.test_username
        data["group"] = None
        magpie_handler.delete_permission_by_user_and_res_id(data["user"], data["resource_id"], data["name"])
        resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
        assert resp.status_code == 200
        self.check_path_perms_and_hardlink(self.output_file, self.hardlink_path, 0o662)
        self.check_path_perms_and_hardlink(ignored_file, ignored_hardlink, 0o660)
        self.check_path_perms_and_hardlink(same_group_file, same_group_hardlink, 0o662)
        utils.check_path_permissions(public_file, 0o660)
        utils.check_path_permissions(public_subfile, 0o660)

        # Test deleting a group permission
        data["name"] = Permission.WRITE.value
        data["user"] = None
        data["group"] = "users"
        magpie_handler.delete_permission_by_grp_and_res_id(data["group"], data["resource_id"], data["name"])
        resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
        assert resp.status_code == 200
        self.check_path_perms_and_hardlink(self.output_file, self.hardlink_path, 0o660)
        self.check_path_perms_and_hardlink(ignored_file, ignored_hardlink, 0o660)
        self.check_path_perms_and_hardlink(same_group_file, same_group_hardlink, 0o660)
        utils.check_path_permissions(public_file, 0o660)
        utils.check_path_permissions(public_subfile, 0o660)

    def test_permission_updates_other_svc(self):
        """
        Tests permission updates on a wpsoutputs resource from a service other than the secure-data-proxy, which should
        not be processed by the filesystem handler.
        """
        magpie_handler = HandlerFactory().get_handler("Magpie")
        # Create resources for the full route
        self.create_secure_data_proxy_service()
        data = {
            "service_name": "other_service",
            "service_type": ServiceAPI.service_type,
            "service_sync_type": ServiceAPI.service_type,
            "service_url": "http://localhost:9000/other_service",
            "configuration": {}
        }
        test_magpie.delete_service(magpie_handler, "other_service")
        other_svc_id = test_magpie.create_service(magpie_handler, data)

        # Create resource associated with the test file, on the other service
        last_res_id = other_svc_id
        routes = re.sub(rf"^{self.wpsoutputs_dir}", "", self.output_file).strip("/")
        for route in routes.split("/"):
            last_res_id = magpie_handler.create_resource(route, Route.resource_type_name, last_res_id)

        data = {
            "event": ValidOperations.DeleteOperation.value,
            "service_name": None,
            "service_type": ServiceAPI.service_type,
            "resource_id": last_res_id,
            "resource_full_name": routes,
            "name": Permission.READ.value,
            "access": Access.ALLOW.value,
            "scope": Scope.MATCH.value,
            "user": self.test_username,
            "group": None
        }
        # Check that a delete event on the resource of the other service does not modify the file permissions.
        resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
        assert resp.status_code == 200
        utils.check_path_permissions(self.output_file, 0o666)

        # Check that a create event on the resource of the other service does not modify the file permissions.
        data["event"] = ValidOperations.CreateOperation.value
        data["access"] = Access.DENY.value
        magpie_handler.create_permission_by_res_id(data["resource_id"], data["name"], data["access"],
                                                   data["scope"], data["user"])
        resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
        assert resp.status_code == 200
        utils.check_path_permissions(self.output_file, 0o666)
