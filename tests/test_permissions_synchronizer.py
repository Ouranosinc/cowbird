import contextlib
import os
from pathlib import Path
import tempfile
import unittest
from collections import Counter
from typing import TYPE_CHECKING

import mock
import pytest
import requests
import yaml
from schema import SchemaError

from dotenv import load_dotenv

from cowbird.api.schemas import ValidOperations
from cowbird.config import (
    MULTI_TOKEN,
    ConfigErrorInvalidResourceKey,
    ConfigErrorInvalidServiceKey,
    ConfigErrorInvalidTokens
)
from cowbird.services import ServiceFactory
from tests import utils

if TYPE_CHECKING:
    from typing import Dict, List, Type

CURR_DIR = Path(__file__).resolve().parent


@pytest.mark.permissions
@pytest.mark.magpie
class TestSyncPermissions(unittest.TestCase):
    """
    Test permissions synchronization.

    These tests parse the sync config and checks that when a permission is created/deleted in the
    `PermissionSynchronizer` the proper permissions are created/deleted for every synchronized service.
    These tests require a running instance of Magpie.
    """

    @classmethod
    def setUpClass(cls):

        load_dotenv(CURR_DIR / "../docker/.env.example")

        cls.grp = "administrators"
        cls.usr = os.getenv("MAGPIE_ADMIN_USER")
        cls.pwd = os.getenv("MAGPIE_ADMIN_PASSWORD")
        cls.url = os.getenv("COWBIRD_TEST_MAGPIE_URL")

        data = {"user_name": cls.usr, "password": cls.pwd}
        resp = requests.post(f"{cls.url}/signin", json=data)
        utils.check_response_basic_info(resp, 200, expected_method="POST")
        cls.cookies = resp.cookies

        cls.test_service_name = "catalog"

        # Reset services instances in case any are left from other test cases
        utils.clear_services_instances()

    def setUp(self):
        # Create test service
        self.test_service_id = self.reset_test_service()

        self.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)  # pylint: disable=R1732
        self.data = {
            "services": {
                "Magpie": {
                    "active": True,
                    "url": self.url,
                    "admin_user": self.usr,
                    "admin_password": self.pwd
                },
                "Thredds": {"active": True}
            }
        }

    def tearDown(self):
        utils.clear_services_instances()
        os.unlink(self.cfg_file.name)
        self.delete_test_service()

    def reset_test_service(self):
        """
        Generates a new test service in Magpie app.
        """
        # First delete the service if it already exists, so it can be recreated
        self.delete_test_service()

        # Create service
        data = {
            "service_name": self.test_service_name,
            "service_type": "thredds",
            "service_sync_type": "thredds",
            "service_url": f"http://localhost:9000/{self.test_service_name}",
            "configuration": {}
        }
        resp = utils.test_request(self.url, "POST", "/services", cookies=self.cookies, json=data)
        body = utils.check_response_basic_info(resp, 201, expected_method="POST")
        return body["service"]["resource_id"]

    def delete_test_service(self):
        """
        Deletes the test service if it exists.
        """
        resp = utils.test_request(self.url, "GET", "/services/" + self.test_service_name, cookies=self.cookies)
        if resp.status_code == 200:
            resp = utils.test_request(self.url, "DELETE", "/services/" + self.test_service_name, cookies=self.cookies)
            utils.check_response_basic_info(resp, 200, expected_method="DELETE")
        else:
            utils.check_response_basic_info(resp, 404, expected_method="GET")

    def create_test_resource(self, resource_name, resource_type, parent_id):
        # type: (str, str, int) -> int
        """
        Creates a test resource in Magpie app.
        """
        data = {
            "resource_name": resource_name,
            "resource_display_name": resource_name,
            "resource_type": resource_type,
            "parent_id": parent_id
        }
        resp = utils.test_request(self.url, "POST", "/resources", cookies=self.cookies, json=data)
        body = utils.check_response_basic_info(resp, 201, expected_method="POST")
        return body["resource"]["resource_id"]

    def create_test_permission(self, resource_id, permission, user_name, group_name):
        # type: (int, Dict, str, str) -> None
        """
        Creates a test permission in Magpie app.
        """
        data = {"permission": permission}
        if user_name:
            resp = utils.test_request(self.url, "POST", f"/users/{user_name}/resources/{resource_id}/permissions",
                                      cookies=self.cookies, json=data)
            utils.check_response_basic_info(resp, 201, expected_method="POST")
        if group_name:
            resp = utils.test_request(self.url, "POST", f"/groups/{group_name}/resources/{resource_id}/permissions",
                                      cookies=self.cookies, json=data)
            utils.check_response_basic_info(resp, 201, expected_method="POST")

    def delete_test_permission(self, resource_id, permission, user_name, group_name):
        # type: (int, Dict, str, str) -> None
        """
        Creates a test permission in Magpie app.
        """
        data = {"permission": permission}
        if user_name:
            resp = utils.test_request(self.url, "DELETE", f"/users/{user_name}/resources/{resource_id}/permissions",
                                      cookies=self.cookies, json=data)
            utils.check_response_basic_info(resp, 200, expected_method="DELETE")
        if group_name:
            resp = utils.test_request(self.url, "DELETE", f"/groups/{group_name}/resources/{resource_id}/permissions",
                                      cookies=self.cookies, json=data)
            utils.check_response_basic_info(resp, 200, expected_method="DELETE")

    def check_user_permissions(self, resource_id, expected_permissions):
        # type: (int, List) -> None
        """
        Checks if the test user has the `expected_permissions` on the `resource_id`.
        """
        resp = utils.test_request(self.url, "GET", f"/users/{self.usr}/resources/{resource_id}/permissions",
                                  cookies=self.cookies)
        body = utils.check_response_basic_info(resp, 200, expected_method="GET")
        assert Counter(body["permission_names"]) == Counter(expected_permissions)

    def check_group_permissions(self, resource_id, expected_permissions):
        # type: (int, List) -> None
        """
        Checks if the test group has the `expected_permissions` on the `resource_id`.
        """
        resp = utils.test_request(self.url, "GET", f"/groups/{self.grp}/resources/{resource_id}/permissions",
                                  cookies=self.cookies)
        body = utils.check_response_basic_info(resp, 200, expected_method="GET")
        assert Counter(body["permission_names"]) == Counter(expected_permissions)

    def test_webhooks_no_tokens(self):
        """
        Tests the permissions synchronization of resources that don't use any tokens in the config.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Thredds0": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "private-dir", "type": "directory"},
                            {"name": "workspace:file0", "type": "file"}],
                        "Thredds1": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "private-dir", "type": "directory"},
                            {"name": "workspace:file1", "type": "file"}],
                        "Thredds2": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "workspace:file2", "type": "file"}],
                        "Thredds3": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "workspace:file3", "type": "file"}],
                        "Thredds4": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "workspace:file4", "type": "file"}]}},
                "permissions_mapping": ["Thredds0 : read <-> Thredds1 : [read-match, write]",  # test implicit formats
                                        # partial duplicate with previous line, should still work
                                        "Thredds0 : read -> Thredds1 : write",
                                        # test explicit permission format in Thredds 2
                                        "Thredds1 : [read-match, write] -> Thredds2 : read-deny-match",
                                        "Thredds3 : read <- Thredds2 : read-deny-match",
                                        "Thredds4 : read -> Thredds1 : [write]"]
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie service instance with new config
        ServiceFactory().create_service("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))

            # Create test resources
            private_dir_res_id = self.create_test_resource("private-dir", "directory", self.test_service_id)
            res_ids = [self.create_test_resource(f"workspace:file{i}", "file", private_dir_res_id) for i in range(2)]
            res_ids += [self.create_test_resource(f"workspace:file{i}", "file", self.test_service_id)
                        for i in range(2, 5)]

            default_read_permission = ["read", "read-allow-recursive"]
            default_write_permission = ["write", "write-allow-recursive"]

            test_cases = [
                {"user": self.usr, "group": None},
                {"user": None, "group": self.grp},
                {"user": self.usr, "group": self.grp}
            ]

            for test_case_usr_grp in test_cases:
                for i in range(5):
                    self.check_user_permissions(res_ids[i], [])
                    self.check_group_permissions(res_ids[i], [])

                resources = {
                    res_ids[0]: {
                        "res_full_name": f"/{self.test_service_name}/private-dir/workspace:file0",
                        "perms": {
                            "read": {"access": "allow",
                                     "scope": "recursive"}}},
                    res_ids[1]: {
                        "res_full_name": f"/{self.test_service_name}/private-dir/workspace:file1",
                        "perms": {
                            "read": {"access": "allow",
                                     "scope": "match"},
                            "write": {"access": "allow",
                                      "scope": "recursive"}}},
                    res_ids[2]: {
                        "res_full_name": f"/{self.test_service_name}/workspace:file2",
                        "perms": {
                            "read": {"access": "deny",
                                     "scope": "match"}}},
                    res_ids[3]: {
                        "res_full_name": f"/{self.test_service_name}/workspace:file3",
                        "perms": {
                            "read": {"access": "allow",
                                     "scope": "recursive"}}},
                    res_ids[4]: {
                        "res_full_name": f"/{self.test_service_name}/workspace:file4",
                        "perms": {
                            "read": {"access": "allow",
                                     "scope": "recursive"}}}
                }

                def check_permission_sync(event, src_res_id, perm_name, expected_perm_dict):
                    """
                    Simulates a permission webhook call and checks if resulting permissions are as expected.
                    """
                    data = {
                        "event": event,
                        "service_name": "thredds",
                        "resource_id": str(src_res_id),
                        "resource_full_name": resources[src_res_id]["res_full_name"],
                        "name": perm_name,
                        "access": resources[src_res_id]["perms"][perm_name]["access"],
                        "scope": resources[src_res_id]["perms"][perm_name]["scope"],
                        "user": test_case_usr_grp["user"],
                        "group": test_case_usr_grp["group"]
                    }
                    resp = utils.test_request(app, "POST", "/webhooks/permissions", json=data)
                    utils.check_response_basic_info(resp, 200, expected_method="POST")
                    for target_res_id in expected_perm_dict:
                        if event == ValidOperations.CreateOperation.value:
                            # For create events, check if permission is created for specified user/group only
                            if test_case_usr_grp["user"]:
                                self.check_user_permissions(res_ids[target_res_id], expected_perm_dict[target_res_id])
                            else:
                                self.check_user_permissions(res_ids[target_res_id], [])
                            if test_case_usr_grp["group"]:
                                self.check_group_permissions(res_ids[target_res_id], expected_perm_dict[target_res_id])
                            else:
                                self.check_group_permissions(res_ids[target_res_id], [])
                        else:
                            if test_case_usr_grp["user"]:
                                self.check_user_permissions(res_ids[target_res_id], expected_perm_dict[target_res_id])
                            if test_case_usr_grp["group"]:
                                self.check_group_permissions(res_ids[target_res_id], expected_perm_dict[target_res_id])

                # Check create permission 0 (0 <-> 1 towards right)
                check_permission_sync(event=ValidOperations.CreateOperation.value,
                                      src_res_id=res_ids[0],
                                      perm_name="read",
                                      expected_perm_dict={
                                          1: default_write_permission + ["read-match", "read-allow-match"]})

                # Check create permission 1 (0 <-> 1 towards left, and 1 -> 2)
                check_permission_sync(event=ValidOperations.CreateOperation.value,
                                      src_res_id=res_ids[1],
                                      perm_name="read",
                                      expected_perm_dict={
                                          0: default_read_permission,
                                          2: ["read-deny-match"]})

                # Check create permission 2 (3 <- 2)
                check_permission_sync(event=ValidOperations.CreateOperation.value,
                                      src_res_id=res_ids[2],
                                      perm_name="read",
                                      expected_perm_dict={
                                          3: default_read_permission})

                # Force create the permission 4, required for the following test.
                self.create_test_permission(res_ids[4], {"name": "read", "access": "allow", "scope": "recursive"},
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])

                # Check delete write permission 1 (0 <-> 1 towards left and 1 -> 2), 0 and 2 should not be deleted,
                # since read permission 1 still exists
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[1],
                                      perm_name="write",
                                      expected_perm_dict={
                                          0: default_read_permission,
                                          2: ["read-deny-match"]})

                # Check delete permission 0 (0 <-> 1 towards right), read permission 1 only should be deleted and
                # write permission 1 should not be deleted, since there is also the mapping 4 -> 1(write),
                # and the permission 4 still exists.
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[0],
                                      perm_name="read",
                                      expected_perm_dict={
                                          1: default_write_permission})

                # Check delete write permission 1 (0 <-> 1 towards left and 1 -> 2), 0 and 2 should be deleted, since
                # read permission 1 does not exist anymore. The sync is still applied, even though 0 and 2 are also
                # mapped to the write permission 1 and the write permission 1 still actually exists in Magpie at this
                # stage of the test, since cowbird assumes that Magpie sends valid webhook events.
                if test_case_usr_grp["user"]:
                    self.check_user_permissions(res_ids[1], default_write_permission)
                if test_case_usr_grp["group"]:
                    self.check_group_permissions(res_ids[1], default_write_permission)
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[1],
                                      perm_name="write",
                                      expected_perm_dict={
                                          0: [],
                                          2: []})

                # Recreate permissions 0 and 2, required for the following tests.
                self.create_test_permission(res_ids[0], {"name": "read", "access": "allow", "scope": "recursive"},
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])
                self.create_test_permission(res_ids[2], {"name": "read", "access": "allow", "scope": "match"},
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])

                # Force delete the permission 4.
                self.delete_test_permission(res_ids[4], {"name": "read", "access": "allow", "scope": "recursive"},
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])

                # Check delete permission 0 (0 <-> 1 towards right), which should now work,
                # since permission 4 was deleted.
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[0],
                                      perm_name="read",
                                      expected_perm_dict={
                                          1: []})

                # Check delete permission 1 (0 <-> 1 towards left and 1 -> 2)
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[1],
                                      perm_name="read",
                                      expected_perm_dict={
                                          0: [],
                                          2: []})

                # Check delete permission 2 (3 <- 2)
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[2],
                                      perm_name="read",
                                      expected_perm_dict={
                                          3: []})

                # Check delete permission 2 (3 <- 2) with permission types different than those from config
                self.create_test_permission(res_ids[3], {"name": "read", "access": "deny", "scope": "recursive"},
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])
                self.create_test_permission(res_ids[3], {"name": "write", "access": "allow", "scope": "recursive"},
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])
                # Read permission is deleted, even if its 'access' (deny) differs with the one sent to Magpie (allow).
                # Magpie deletes the permission even if the access or the scope is different than the one sent
                # in the patch permissions Magpie request.
                # Only the write permission remains.
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[2],
                                      perm_name="read",
                                      expected_perm_dict={
                                          3: default_write_permission})
                self.delete_test_permission(res_ids[3], {"name": "write", "access": "allow", "scope": "recursive"},
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])

    def test_webhooks_valid_tokens(self):
        """
        Tests the permissions synchronization of resources that use valid tokens in the config.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Thredds_file_src": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "private", "type": "directory"},
                            {"name": MULTI_TOKEN, "type": "directory"},
                            {"name": "{file}", "type": "file"}],
                        "Thredds_file_target": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"},
                            {"name": "{file}", "type": "file"}],
                        "Thredds_dir_src": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "private", "type": "directory"},
                            {"name": MULTI_TOKEN, "type": "directory"}],
                        "Thredds_dir_target": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}],
                        "Thredds_named_dir_src": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "named_dir1", "type": "directory"},
                            {"name": "{dir1}", "type": "directory"},
                            {"name": "{dir2}", "type": "directory"}],
                        "Thredds_named_dir_target": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "named_dir2", "type": "directory"},
                            {"name": "{dir2}", "type": "directory"},
                            {"name": "{dir1}", "type": "directory"}]}},
                "permissions_mapping": ["Thredds_file_src : read <-> Thredds_file_target : read",
                                        "Thredds_dir_src : read <-> Thredds_dir_target : read",
                                        "Thredds_named_dir_src : read <-> Thredds_named_dir_target : read"]
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie service instance with new config
        ServiceFactory().create_service("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))

            # Create test resources
            dir_src_res_id = self.create_test_resource("private", "directory", self.test_service_id)
            parent_res_id = self.create_test_resource("dir1", "directory", dir_src_res_id)
            parent_res_id = self.create_test_resource("dir2", "directory", parent_res_id)
            file_src_res_id = self.create_test_resource("workspace_file", "file", parent_res_id)

            dir_target_res_id = self.test_service_id
            parent_res_id = self.create_test_resource("dir1", "directory", self.test_service_id)
            parent_res_id = self.create_test_resource("dir2", "directory", parent_res_id)
            file_target_res_id = self.create_test_resource("workspace_file", "file", parent_res_id)

            parent_res_id = self.create_test_resource("named_dir1", "directory", self.test_service_id)
            parent_res_id = self.create_test_resource("dir1", "directory", parent_res_id)
            named_dir_src_res_id = self.create_test_resource("dir2", "directory", parent_res_id)
            parent_res_id = self.create_test_resource("named_dir2", "directory", self.test_service_id)
            parent_res_id = self.create_test_resource("dir2", "directory", parent_res_id)
            named_dir_target_res_id = self.create_test_resource("dir1", "directory", parent_res_id)

            # Create permissions for 1st mapping case, src resource should match with a MULTI_TOKEN that
            # uses 0 segment occurrence
            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": "thredds",
                "resource_id": str(dir_src_res_id),
                "resource_full_name": f"/{self.test_service_name}/private",
                "name": "read",
                "access": "allow",
                "scope": "recursive",
                "user": self.usr,
                "group": None
            }
            resp = utils.test_request(app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")

            # Check if only corresponding permissions were created
            self.check_user_permissions(dir_target_res_id, ["read", "read-allow-recursive"])
            self.check_user_permissions(file_target_res_id, [])

            # Create and check permissions with 2nd mapping case
            data["resource_id"] = str(file_src_res_id)
            data["resource_full_name"] = f"/{self.test_service_name}/private/dir1/dir2/workspace_file"

            resp = utils.test_request(app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            self.check_user_permissions(file_target_res_id, ["read", "read-allow-recursive"])

            # Create and check permissions with 3rd mapping case
            data["resource_id"] = str(named_dir_src_res_id)
            data["resource_full_name"] = f"/{self.test_service_name}/named_dir1/dir1/dir2"

            resp = utils.test_request(app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            self.check_user_permissions(named_dir_target_res_id, ["read", "read-allow-recursive"])

    def test_webhooks_invalid_multimatch(self):
        """
        Tests the invalid case where a resource in the incoming webhook matches multiple resource keys in the config.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Thredds_match1": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "{dir1}", "type": "directory"},
                            {"name": "{dir2}", "type": "directory"}],
                        "Thredds_match2": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "{dir2}", "type": "directory"},
                            {"name": "{dir1}", "type": "directory"}]}},
                "permissions_mapping": ["Thredds_match1 : read -> Thredds_match2 : read"]
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie service instance with new config
        ServiceFactory().create_service("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))
            # Create test resources
            parent_id = self.create_test_resource("dir1", "directory", self.test_service_id)
            src_res_id = self.create_test_resource("dir2", "directory", parent_id)

            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": "thredds",
                "resource_id": str(src_res_id),
                "resource_full_name": f"/{self.test_service_name}/dir1/dir2",
                "name": "read",
                "access": "allow",
                "scope": "recursive",
                "user": self.usr,
                "group": None
            }

            # Try creating permissions
            resp = utils.test_request(app, "POST", "/webhooks/permissions", json=data, expect_errors=True)
            # Should create an error since input resource to synchronize can match with both resources in config
            utils.check_response_basic_info(resp, 500, expected_method="POST")

    def test_webhooks_no_match(self):
        """
        Tests the invalid case where a resource found in the incoming webhook finds no match in the config.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Thredds_match1": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}],
                        "Thredds_match2": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "dir", "type": "directory"},
                            {"name": MULTI_TOKEN, "type": "directory"}]}},
                "permissions_mapping": ["Thredds_match1 : read -> Thredds_match2 : read"]
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie service instance with new config
        ServiceFactory().create_service("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))
            # Create test resources
            src_res_id = self.create_test_resource("dir", "file", self.test_service_id)

            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": "thredds",
                "resource_id": str(src_res_id),
                "resource_full_name": f"/{self.test_service_name}/dir",
                "name": "read",
                "access": "allow",
                "scope": "recursive",
                "user": self.usr,
                "group": None
            }

            # Try creating permissions
            resp = utils.test_request(app, "POST", "/webhooks/permissions", json=data, expect_errors=True)
            # Should create an error since input resource doesn't match the type of resources found in config
            utils.check_response_basic_info(resp, 500, expected_method="POST")

    def test_webhooks_invalid_service(self):
        """
        Tests the case where a service used in the `sync_permissions` section of the config is invalid.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "NotAMagpieService": {
                        "Invalid": [
                            {"name": "catalog", "type": "service"},
                            {"name": "dir", "type": "directory"}]}},
                "permissions_mapping": []
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))

        utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Try creating Magpie handler with invalid config
        utils.check_raises(lambda: ServiceFactory().create_service("Magpie"),
                           ConfigErrorInvalidServiceKey, msg="invalid config file should raise")


def check_config(config_data, expected_exception_type=None):
    # type: (Dict, Type[Exception]) -> None
    """
    Checks if the config loads without error, or if it triggers the expected exception in the case of an invalid config.
    """
    cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)
    with cfg_file as f:
        f.write(yaml.safe_dump(config_data))
    if expected_exception_type:
        utils.check_raises(lambda: utils.get_test_app(settings={"cowbird.config_path": f.name}),
                           expected_exception_type, msg="invalid config file should raise")
    else:
        utils.get_test_app(settings={"cowbird.config_path": f.name})
    os.unlink(cfg_file.name)


@pytest.mark.permissions
class TestSyncPermissionsConfig(unittest.TestCase):
    """
    Tests different config setups for permissions synchronization.
    """

    def setUp(self):
        self.data = {
            "services": {
                "Magpie": {"active": True, "url": "",
                           "admin_user": "admin", "admin_password": "qwertyqwerty"},
                "Thredds": {"active": True},
                "Geoserver": {"active": True}
            }
        }

    def test_not_unique_multitoken(self):
        """
        Tests if config respects the constraint of using maximum one `MULTI_TOKEN` in a single resource.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Valid_multitoken": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}
                        ]}},
                "permissions_mapping": []
            }
        }
        check_config(self.data)

        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Invalid_multitoken": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"},
                            {"name": MULTI_TOKEN, "type": "directory"}
                        ]}},
                "permissions_mapping": []
            }
        }
        check_config(self.data, ConfigErrorInvalidTokens)

    def test_not_unique_named_token(self):
        """
        Tests an invalid config where duplicate named tokens are used in a single resource.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Duplicate_tokens": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir_var}", "type": "directory"},
                            {"name": "{dir_var}", "type": "directory"}
                        ]}},
                "permissions_mapping": []
            }
        }
        check_config(self.data, ConfigErrorInvalidTokens)

    def test_unknown_res_key(self):
        """
        Tests an invalid config where an unknown resource key is found in the permissions_mapping.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "ValidResource": [
                            {"name": "catalog", "type": "service"}
                        ]}},
                "permissions_mapping": ["ValidResource : read <-> UnknownResource : read"]
            }
        }
        check_config(self.data, ConfigErrorInvalidResourceKey)

    def test_duplicate_resource_key(self):
        """
        Tests an invalid config where the same resource key is used for different resources.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "DuplicateResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": "dir", "type": "directory"}],
                        "OtherResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": "file", "type": "file"}]},
                    "geoserver": {
                        "DuplicateResource": [
                            {"name": "catalog", "type": "workspace"},
                            {"name": "dir", "type": "workspace"}]}
                },
                "permissions_mapping": ["DuplicateResource : read <-> OtherResource : read"]
            }
        }
        check_config(self.data, ConfigErrorInvalidResourceKey)

    def test_invalid_mapping_format(self):
        """
        Tests an invalid config where a permissions_mapping uses an invalid format.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "ValidResource": [
                            {"name": "catalog", "type": "service"}
                        ],
                        "ValidResource2": [
                            {"name": "catalog", "type": "service"}
                        ]}},
                "permissions_mapping": ["ValidResource : read <-> Invalid-format"]
            }
        }
        check_config(self.data, SchemaError)

    def test_multi_token_bidirectional(self):
        """
        Tests the usage of MULTI_TOKEN in a bidirectional mapping.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "TokenizedResource1": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}],
                        "TokenizedResource2": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"},
                            {"name": "file", "type": "file"}
                        ]}},
                "permissions_mapping": ["TokenizedResource1 : read <-> TokenizedResource2 : read"]
            }
        }
        check_config(self.data)

        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "TokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}],
                        "UntokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": "file", "type": "file"}
                        ]}},
                "permissions_mapping": ["TokenizedResource : read <-> UntokenizedResource : read"]
            }
        }
        check_config(self.data, ConfigErrorInvalidTokens)

    def test_unidirectional_multi_token(self):
        """
        Tests the usage of MULTI_TOKEN in a unidirectional mapping.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "TokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}],
                        "UntokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": "file", "type": "file"}
                        ]}},
                "permissions_mapping": ["TokenizedResource : read -> UntokenizedResource : read"]
            }
        }
        check_config(self.data)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            ["UntokenizedResource : read -> TokenizedResource : read"]
        check_config(self.data, ConfigErrorInvalidTokens)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            ["TokenizedResource : read <- UntokenizedResource : read"]
        check_config(self.data, ConfigErrorInvalidTokens)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            ["UntokenizedResource : read <- TokenizedResource : read"]
        check_config(self.data)

    def test_bidirectional_named_tokens(self):
        """
        Tests config with a bidirectional mapping that uses named tokens.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Resource1": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "{dir2_var}", "type": "directory"}],
                        "Resource2": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir2_var}", "type": "directory"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "dir2", "type": "directory"}
                        ]}},
                "permissions_mapping": ["Resource1 : read <-> Resource2 : read"]
            }
        }
        check_config(self.data)

        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Resource1": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "{dir2_var}", "type": "directory"}],
                        "Resource2": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "dir2", "type": "directory"}
                        ]}},
                "permissions_mapping": ["Resource1 : read <-> Resource2 : read"]
            }
        }
        check_config(self.data, ConfigErrorInvalidTokens)

    def test_unidirectional_named_tokens(self):
        """
        Tests config with a unidirectional mapping that uses named tokens.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Resource1": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "{dir2_var}", "type": "directory"}],
                        "Resource2": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "dir2", "type": "directory"}
                        ]}},
                "permissions_mapping": ["Resource1 : read -> Resource2 : read"]
            }
        }
        check_config(self.data)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            ["Resource2 : read -> Resource1 : read"]
        check_config(self.data, ConfigErrorInvalidTokens)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            ["Resource1 : read <- Resource2 : read"]
        check_config(self.data, ConfigErrorInvalidTokens)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            ["Resource2 : read <- Resource1 : read"]
        check_config(self.data)

    def test_cross_service_mappings(self):
        """
        Tests config that uses mappings between permissions of different services.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "ThreddsMultiTokenResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}],
                        "ThreddsNamedTokenResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "{dir2_var}", "type": "directory"}]
                        },
                    "geoserver": {
                        "GeoserverMultiTokenResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"},
                            {"name": "file", "type": "file"}],
                        "GeoserverUntokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": "file", "type": "file"}],
                        "GeoserverNamedTokenResource1": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "dir2", "type": "directory"}],
                        "GeoserverNamedTokenResource2": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "{dir2_var}", "type": "directory"}]
                    }},
                "permissions_mapping": ["ThreddsMultiTokenResource : read -> GeoserverUntokenizedResource : read",
                                        "ThreddsMultiTokenResource : read <-> GeoserverMultiTokenResource : read",
                                        "ThreddsNamedTokenResource : read -> GeoserverUntokenizedResource : read",
                                        "ThreddsNamedTokenResource : read -> GeoserverNamedTokenResource1 : read",
                                        "ThreddsNamedTokenResource : read <-> GeoserverNamedTokenResource2 : read"]
            }
        }
        check_config(self.data)
