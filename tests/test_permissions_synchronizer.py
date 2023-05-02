import contextlib
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import mock
import pytest
import yaml
from dotenv import load_dotenv
from schema import SchemaError

from cowbird.api.schemas import ValidOperations
from cowbird.config import (
    MULTI_TOKEN,
    ConfigErrorInvalidResourceKey,
    ConfigErrorInvalidServiceKey,
    ConfigErrorInvalidTokens
)
from cowbird.handlers import HandlerFactory
from magpie.models import Directory, File, Service, Workspace
from magpie.permissions import Access, Permission, Scope
from magpie.services import ServiceGeoserver, ServiceTHREDDS
from tests import test_magpie
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
        cls.test_service_name = "catalog"

        # Reset handlers instances in case any are left from other test cases
        utils.clear_handlers_instances()

    def setUp(self):
        self.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)  # pylint: disable=R1732
        self.data = {
            "handlers": {
                "Magpie": {
                    "active": True,
                    "url": self.url,
                    "admin_user": self.usr,
                    "admin_password": self.pwd
                },
                "Thredds": {"active": True}
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        # Set environment variables with config
        utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Create new magpie handler instance with new config
        self.magpie = HandlerFactory().create_handler("Magpie")
        # Create test service
        self.test_service_id = self.reset_test_service()

    def tearDown(self):
        utils.clear_handlers_instances()
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
            "service_type": ServiceTHREDDS.service_type,
            "service_sync_type": ServiceTHREDDS.service_type,
            "service_url": f"http://localhost:9000/{self.test_service_name}",
            "configuration": {}
        }
        return test_magpie.create_service(self.magpie, data)

    def delete_test_service(self):
        """
        Deletes the test service if it exists.
        """
        test_magpie.delete_service(self.magpie, self.test_service_name)

    def create_test_permission(self, resource_id, permission, user_name, group_name):
        # type: (int, Dict, str, str) -> None
        """
        Creates a test permission in Magpie app.
        """
        data = {"permission": permission}
        if user_name:
            self.magpie.create_permission_by_user_and_res_id(user_name, resource_id, data)
        if group_name:
            self.magpie.create_permission_by_grp_and_res_id(group_name, resource_id, data)

    def delete_test_permission(self, resource_id, permission_name, user_name, group_name):
        # type: (int, str, str, str) -> None
        """
        Creates a test permission in Magpie app.
        """
        if user_name:
            self.magpie.delete_permission_by_user_and_res_id(user_name, resource_id, permission_name)
        if group_name:
            self.magpie.delete_permission_by_grp_and_res_id(group_name, resource_id, permission_name)

    def check_user_permissions(self, resource_id, expected_permissions):
        # type: (int, List) -> None
        """
        Checks if the test user has the `expected_permissions` on the `resource_id`.
        """
        permissions = self.magpie.get_user_permissions_by_res_id(self.usr, resource_id)
        assert Counter(permissions["permission_names"]) == Counter(expected_permissions)

    def check_group_permissions(self, resource_id, expected_permissions):
        # type: (int, List) -> None
        """
        Checks if the test group has the `expected_permissions` on the `resource_id`.
        """
        permissions = self.magpie.get_group_permissions_by_res_id(self.grp, resource_id)
        assert Counter(permissions["permission_names"]) == Counter(expected_permissions)

    def test_webhooks_no_tokens(self):
        """
        Tests the permissions synchronization of resources that don't use any tokens in the config.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    ServiceTHREDDS.service_type: {
                        "Thredds0": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": "private-dir", "type": Directory.resource_type_name},
                            {"name": "workspace:file0", "type": File.resource_type_name}],
                        "Thredds1": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": "private-dir", "type": Directory.resource_type_name},
                            {"name": "workspace:file1", "type": File.resource_type_name}],
                        "Thredds2": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": "workspace:file2", "type": File.resource_type_name}],
                        "Thredds3": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": "workspace:file3", "type": File.resource_type_name}],
                        "Thredds4": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": "workspace:file4", "type": File.resource_type_name}]}},
                "permissions_mapping": [
                    # test implicit formats
                    f"Thredds0 : {Permission.READ.value} <-> "
                        f"Thredds1 : [{Permission.READ.value}-{Scope.MATCH.value}, {Permission.WRITE.value}]",
                    # partial duplicate with previous line, should still work
                    f"Thredds0 : {Permission.READ.value} -> Thredds1 : {Permission.WRITE.value}",
                    # test explicit permission format in Thredds 2
                    f"Thredds1 : [{Permission.READ.value}-{Scope.MATCH.value}, {Permission.WRITE.value}] -> "
                        f"Thredds2 : {Permission.READ.value}-{Access.DENY.value}-{Scope.MATCH.value}",
                    f"Thredds3 : {Permission.READ.value} <- "
                        f"Thredds2 : {Permission.READ.value}-{Access.DENY.value}-{Scope.MATCH.value}",
                    f"Thredds4 : {Permission.READ.value} -> Thredds1 : [{Permission.WRITE.value}]"]
            }
        }
        with open(self.cfg_file.name, mode="w", encoding="utf-8") as f:
            f.write(yaml.safe_dump(self.data))
        app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie handler instance with new config
        HandlerFactory().create_handler("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.handlers.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyHandler))

            # Create test resources
            private_dir_res_id = self.magpie.create_resource("private-dir", Directory.resource_type_name, self.test_service_id)
            res_ids = [self.magpie.create_resource(f"workspace:file{i}", File.resource_type_name, private_dir_res_id) for i in range(2)]
            res_ids += [self.magpie.create_resource(f"workspace:file{i}", File.resource_type_name, self.test_service_id)
                        for i in range(2, 5)]

            default_read_permission = [Permission.READ.value,
                                       f"{Permission.READ.value}-{Access.ALLOW.value}-{Scope.RECURSIVE.value}"]
            default_write_permission = [Permission.WRITE.value,
                                        f"{Permission.WRITE.value}-{Access.ALLOW.value}-{Scope.RECURSIVE.value}"]

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
                            Permission.READ.value: {"access": Access.ALLOW.value,
                                                    "scope": Scope.RECURSIVE.value}}},
                    res_ids[1]: {
                        "res_full_name": f"/{self.test_service_name}/private-dir/workspace:file1",
                        "perms": {
                            Permission.READ.value: {"access": Access.ALLOW.value,
                                                    "scope": Scope.MATCH.value},
                            Permission.WRITE.value: {"access": Access.ALLOW.value,
                                                     "scope": Scope.RECURSIVE.value}}},
                    res_ids[2]: {
                        "res_full_name": f"/{self.test_service_name}/workspace:file2",
                        "perms": {
                            Permission.READ.value: {"access": Access.DENY.value,
                                                    "scope": Scope.MATCH.value}}},
                    res_ids[3]: {
                        "res_full_name": f"/{self.test_service_name}/workspace:file3",
                        "perms": {
                            Permission.READ.value: {"access": Access.ALLOW.value,
                                                    "scope": Scope.RECURSIVE.value}}},
                    res_ids[4]: {
                        "res_full_name": f"/{self.test_service_name}/workspace:file4",
                        "perms": {
                            Permission.READ.value: {"access": Access.ALLOW.value,
                                                    "scope": Scope.RECURSIVE.value}}}
                }

                def check_permission_sync(event, src_res_id, perm_name, expected_perm_dict):
                    """
                    Simulates a permission webhook call and checks if resulting permissions are as expected.
                    """
                    data = {
                        "event": event,
                        "service_name": "thredds",
                        "resource_id": src_res_id,
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
                                      perm_name=Permission.READ.value,
                                      expected_perm_dict={
                                          1: default_write_permission +
                                          [f"{Permission.READ.value}-{Scope.MATCH.value}",
                                              f"{Permission.READ.value}-{Access.ALLOW.value}-{Scope.MATCH.value}"]})

                # Check create permission 1 (0 <-> 1 towards left, and 1 -> 2)
                check_permission_sync(event=ValidOperations.CreateOperation.value,
                                      src_res_id=res_ids[1],
                                      perm_name=Permission.READ.value,
                                      expected_perm_dict={
                                          0: default_read_permission,
                                          2: [f"{Permission.READ.value}-{Access.DENY.value}-{Scope.MATCH.value}"]})

                # Check create permission 2 (3 <- 2)
                check_permission_sync(event=ValidOperations.CreateOperation.value,
                                      src_res_id=res_ids[2],
                                      perm_name=Permission.READ.value,
                                      expected_perm_dict={
                                          3: default_read_permission})

                # Force create the permission 4, required for the following test.
                self.create_test_permission(res_ids[4], {"name": Permission.READ.value,
                                                         "access": Access.ALLOW.value,
                                                         "scope": Scope.RECURSIVE.value},
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])

                # Check delete write permission 1 (0 <-> 1 towards left and 1 -> 2), 0 and 2 should not be deleted,
                # since read permission 1 still exists
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[1],
                                      perm_name=Permission.WRITE.value,
                                      expected_perm_dict={
                                          0: default_read_permission,
                                          2: [f"{Permission.READ.value}-{Access.DENY.value}-{Scope.MATCH.value}"]})

                # Check delete permission 0 (0 <-> 1 towards right), read permission 1 only should be deleted and
                # write permission 1 should not be deleted, since there is also the mapping 4 -> 1(write),
                # and the permission 4 still exists.
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[0],
                                      perm_name=Permission.READ.value,
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
                                      perm_name=Permission.WRITE.value,
                                      expected_perm_dict={
                                          0: [],
                                          2: []})

                # Recreate permissions 0 and 2, required for the following tests.
                self.create_test_permission(res_ids[0], {"name": Permission.READ.value,
                                                         "access": Access.ALLOW.value,
                                                         "scope": Scope.RECURSIVE.value},
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])
                self.create_test_permission(res_ids[2], {"name": Permission.READ.value,
                                                         "access": Access.ALLOW.value,
                                                         "scope": Scope.MATCH.value},
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])

                # Force delete the permission 4.
                self.delete_test_permission(res_ids[4], Permission.READ.value,
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])

                # Check delete permission 0 (0 <-> 1 towards right), which should now work,
                # since permission 4 was deleted.
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[0],
                                      perm_name=Permission.READ.value,
                                      expected_perm_dict={
                                          1: []})

                # Check delete permission 1 (0 <-> 1 towards left and 1 -> 2)
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[1],
                                      perm_name=Permission.READ.value,
                                      expected_perm_dict={
                                          0: [],
                                          2: []})

                # Check delete permission 2 (3 <- 2)
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[2],
                                      perm_name=Permission.READ.value,
                                      expected_perm_dict={
                                          3: []})

                # Check delete permission 2 (3 <- 2) with permission types different than those from config
                self.create_test_permission(res_ids[3], {"name": Permission.READ.value,
                                                         "access": Access.DENY.value,
                                                         "scope": Scope.RECURSIVE.value},
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])
                self.create_test_permission(res_ids[3], {"name": Permission.WRITE.value,
                                                         "access": Access.ALLOW.value,
                                                         "scope": Scope.RECURSIVE.value},
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])
                # Read permission is deleted, even if its 'access' (deny) differs with the one sent to Magpie (allow).
                # Magpie deletes the permission even if the access or the scope is different than the one sent
                # in the patch permissions Magpie request.
                # Only the write permission remains.
                check_permission_sync(event=ValidOperations.DeleteOperation.value,
                                      src_res_id=res_ids[2],
                                      perm_name=Permission.READ.value,
                                      expected_perm_dict={
                                          3: default_write_permission})
                self.delete_test_permission(res_ids[3], Permission.WRITE.value,
                                            test_case_usr_grp["user"], test_case_usr_grp["group"])

    def test_webhooks_valid_tokens(self):
        """
        Tests the permissions synchronization of resources that use valid tokens in the config.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    ServiceTHREDDS.service_type: {
                        "Thredds_file_src": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": "private", "type": Directory.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name},
                            {"name": "{file}", "type": File.resource_type_name}],
                        "Thredds_file_target": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name},
                            {"name": "{file}", "type": File.resource_type_name}],
                        "Thredds_dir_src": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": "private", "type": Directory.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name}],
                        "Thredds_dir_target": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name}],
                        "Thredds_named_dir_src": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": "named_dir1", "type": Directory.resource_type_name},
                            {"name": "{dir1}", "type": Directory.resource_type_name},
                            {"name": "{dir2}", "type": Directory.resource_type_name}],
                        "Thredds_named_dir_target": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": "named_dir2", "type": Directory.resource_type_name},
                            {"name": "{dir2}", "type": Directory.resource_type_name},
                            {"name": "{dir1}", "type": Directory.resource_type_name}]}},
                "permissions_mapping": [f"Thredds_file_src : {Permission.READ.value} <-> "
                                            f"Thredds_file_target : {Permission.READ.value}",
                                        f"Thredds_dir_src : {Permission.READ.value} <-> "
                                            f"Thredds_dir_target : {Permission.READ.value}",
                                        f"Thredds_named_dir_src : {Permission.READ.value} <-> "
                                            f"Thredds_named_dir_target : {Permission.READ.value}"]
            }
        }
        with open(self.cfg_file.name, mode="w", encoding="utf-8") as f:
            f.write(yaml.safe_dump(self.data))
        app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie handler instance with new config
        HandlerFactory().create_handler("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.handlers.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyHandler))

            # Create test resources
            dir_src_res_id = self.magpie.create_resource("private", Directory.resource_type_name, self.test_service_id)
            parent_res_id = self.magpie.create_resource("dir1", Directory.resource_type_name, dir_src_res_id)
            parent_res_id = self.magpie.create_resource("dir2", Directory.resource_type_name, parent_res_id)
            file_src_res_id = self.magpie.create_resource("workspace_file", File.resource_type_name, parent_res_id)

            dir_target_res_id = self.test_service_id
            parent_res_id = self.magpie.create_resource("dir1", Directory.resource_type_name, self.test_service_id)
            parent_res_id = self.magpie.create_resource("dir2", Directory.resource_type_name, parent_res_id)
            file_target_res_id = self.magpie.create_resource("workspace_file", File.resource_type_name, parent_res_id)

            parent_res_id = self.magpie.create_resource("named_dir1", Directory.resource_type_name, self.test_service_id)
            parent_res_id = self.magpie.create_resource("dir1", Directory.resource_type_name, parent_res_id)
            named_dir_src_res_id = self.magpie.create_resource("dir2", Directory.resource_type_name, parent_res_id)
            parent_res_id = self.magpie.create_resource("named_dir2", Directory.resource_type_name, self.test_service_id)
            parent_res_id = self.magpie.create_resource("dir2", Directory.resource_type_name, parent_res_id)
            named_dir_target_res_id = self.magpie.create_resource("dir1", Directory.resource_type_name, parent_res_id)

            # Create permissions for 1st mapping case, src resource should match with a MULTI_TOKEN that
            # uses 0 segment occurrence
            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": ServiceTHREDDS.service_type,
                "resource_id": dir_src_res_id,
                "resource_full_name": f"/{self.test_service_name}/private",
                "name": Permission.READ.value,
                "access": Access.ALLOW.value,
                "scope": Scope.RECURSIVE.value,
                "user": self.usr,
                "group": None
            }
            resp = utils.test_request(app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")

            # Check if only corresponding permissions were created
            self.check_user_permissions(dir_target_res_id,
                                        [Permission.READ.value,
                                         f"{Permission.READ.value}-{Access.ALLOW.value}-{Scope.RECURSIVE.value}"])
            self.check_user_permissions(file_target_res_id, [])

            # Create and check permissions with 2nd mapping case
            data["resource_id"] = file_src_res_id
            data["resource_full_name"] = f"/{self.test_service_name}/private/dir1/dir2/workspace_file"

            resp = utils.test_request(app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            self.check_user_permissions(file_target_res_id,
                                        [Permission.READ.value,
                                         f"{Permission.READ.value}-{Access.ALLOW.value}-{Scope.RECURSIVE.value}"])

            # Create and check permissions with 3rd mapping case
            data["resource_id"] = named_dir_src_res_id
            data["resource_full_name"] = f"/{self.test_service_name}/named_dir1/dir1/dir2"

            resp = utils.test_request(app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            self.check_user_permissions(named_dir_target_res_id,
                                        [Permission.READ.value,
                                         f"{Permission.READ.value}-{Access.ALLOW.value}-{Scope.RECURSIVE.value}"])

    def test_webhooks_invalid_multimatch(self):
        """
        Tests the invalid case where a resource in the incoming webhook matches multiple resource keys in the config.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    ServiceTHREDDS.service_type: {
                        "Thredds_match1": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": "{dir1}", "type": Directory.resource_type_name},
                            {"name": "{dir2}", "type": Directory.resource_type_name}],
                        "Thredds_match2": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": "{dir2}", "type": Directory.resource_type_name},
                            {"name": "{dir1}", "type": Directory.resource_type_name}]}},
                "permissions_mapping": [f"Thredds_match1 : {Permission.READ.value} -> "
                                        f"Thredds_match2 : {Permission.READ.value}"]
            }
        }
        with open(self.cfg_file.name, mode="w", encoding="utf-8") as f:
            f.write(yaml.safe_dump(self.data))
        app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie handler instance with new config
        HandlerFactory().create_handler("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.handlers.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyHandler))
            # Create test resources
            parent_id = self.magpie.create_resource("dir1", Directory.resource_type_name, self.test_service_id)
            src_res_id = self.magpie.create_resource("dir2", Directory.resource_type_name, parent_id)

            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": ServiceTHREDDS.service_type,
                "resource_id": src_res_id,
                "resource_full_name": f"/{self.test_service_name}/dir1/dir2",
                "name": Permission.READ.value,
                "access": Access.ALLOW.value,
                "scope": Scope.RECURSIVE.value,
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
                    ServiceTHREDDS.service_type: {
                        "Thredds_match1": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name}],
                        "Thredds_match2": [
                            {"name": self.test_service_name, "type": Service.resource_type_name},
                            {"name": "dir", "type": Directory.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name}]}},
                "permissions_mapping": [f"Thredds_match1 : {Permission.READ.value} -> "
                                        f"Thredds_match2 : {Permission.READ.value}"]
            }
        }
        with open(self.cfg_file.name, mode="w", encoding="utf-8") as f:
            f.write(yaml.safe_dump(self.data))
        app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie handler instance with new config
        HandlerFactory().create_handler("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.handlers.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyHandler))
            # Create test resources
            src_res_id = self.magpie.create_resource("dir", File.resource_type_name, self.test_service_id)

            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": ServiceTHREDDS.service_type,
                "resource_id": src_res_id,
                "resource_full_name": f"/{self.test_service_name}/dir",
                "name": Permission.READ.value,
                "access": Access.ALLOW.value,
                "scope": Scope.RECURSIVE.value,
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
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "dir", "type": Directory.resource_type_name}]}},
                "permissions_mapping": []
            }
        }
        with open(self.cfg_file.name, mode="w", encoding="utf-8") as f:
            f.write(yaml.safe_dump(self.data))

        utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Try creating Magpie handler with invalid config
        utils.check_raises(lambda: HandlerFactory().create_handler("Magpie"),
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
            "handlers": {
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
                    ServiceTHREDDS.service_type: {
                        "Valid_multitoken": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name}
                        ]}},
                "permissions_mapping": []
            }
        }
        check_config(self.data)

        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    ServiceTHREDDS.service_type: {
                        "Invalid_multitoken": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name}
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
                    ServiceTHREDDS.service_type: {
                        "Duplicate_tokens": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "{dir_var}", "type": Directory.resource_type_name},
                            {"name": "{dir_var}", "type": Directory.resource_type_name}
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
                    ServiceTHREDDS.service_type: {
                        "ValidResource": [
                            {"name": "catalog", "type": Service.resource_type_name}
                        ]}},
                "permissions_mapping": [f"ValidResource : {Permission.READ.value} <-> "
                                        f"UnknownResource : f{Permission.READ.value}"]
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
                    ServiceTHREDDS.service_type: {
                        "DuplicateResource": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "dir", "type": Directory.resource_type_name}],
                        "OtherResource": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "file", "type": File.resource_type_name}]},
                    ServiceGeoserver.service_type: {
                        "DuplicateResource": [
                            {"name": "catalog", "type": Workspace.resource_type_name},
                            {"name": "dir", "type": Workspace.resource_type_name}]}
                },
                "permissions_mapping": [f"DuplicateResource : {Permission.READ.value} <-> "
                                        f"OtherResource : {Permission.READ.value}"]
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
                    ServiceTHREDDS.service_type: {
                        "ValidResource": [
                            {"name": "catalog", "type": Service.resource_type_name}
                        ],
                        "ValidResource2": [
                            {"name": "catalog", "type": Service.resource_type_name}
                        ]}},
                "permissions_mapping": [f"ValidResource : {Permission.READ.value} <-> Invalid-format"]
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
                    ServiceTHREDDS.service_type: {
                        "TokenizedResource1": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name}],
                        "TokenizedResource2": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name},
                            {"name": "file", "type": File.resource_type_name}
                        ]}},
                "permissions_mapping": [f"TokenizedResource1 : {Permission.READ.value} <-> "
                                        f"TokenizedResource2 : {Permission.READ.value}"]
            }
        }
        check_config(self.data)

        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    ServiceTHREDDS.service_type: {
                        "TokenizedResource": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name}],
                        "UntokenizedResource": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "file", "type": File.resource_type_name}
                        ]}},
                "permissions_mapping": [f"TokenizedResource : {Permission.READ.value} <-> "
                                        f"UntokenizedResource : {Permission.READ.value}"]
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
                    ServiceTHREDDS.service_type: {
                        "TokenizedResource": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name}],
                        "UntokenizedResource": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "file", "type": File.resource_type_name}
                        ]}},
                "permissions_mapping": [f"TokenizedResource : {Permission.READ.value} -> "
                                        f"UntokenizedResource : {Permission.READ.value}"]
            }
        }
        check_config(self.data)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            [f"UntokenizedResource : {Permission.READ.value} -> TokenizedResource : {Permission.READ.value}"]
        check_config(self.data, ConfigErrorInvalidTokens)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            [f"TokenizedResource : {Permission.READ.value} <- UntokenizedResource : {Permission.READ.value}"]
        check_config(self.data, ConfigErrorInvalidTokens)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            [f"UntokenizedResource : {Permission.READ.value} <- TokenizedResource : {Permission.READ.value}"]
        check_config(self.data)

    def test_bidirectional_named_tokens(self):
        """
        Tests config with a bidirectional mapping that uses named tokens.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    ServiceTHREDDS.service_type: {
                        "Resource1": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "{dir1_var}", "type": Directory.resource_type_name},
                            {"name": "{dir2_var}", "type": Directory.resource_type_name}],
                        "Resource2": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "{dir2_var}", "type": Directory.resource_type_name},
                            {"name": "{dir1_var}", "type": Directory.resource_type_name},
                            {"name": "dir2", "type": Directory.resource_type_name}
                        ]}},
                "permissions_mapping": [f"Resource1 : {Permission.READ.value} <-> Resource2 : {Permission.READ.value}"]
            }
        }
        check_config(self.data)

        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    ServiceTHREDDS.service_type: {
                        "Resource1": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "{dir1_var}", "type": Directory.resource_type_name},
                            {"name": "{dir2_var}", "type": Directory.resource_type_name}],
                        "Resource2": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "{dir1_var}", "type": Directory.resource_type_name},
                            {"name": "dir2", "type": Directory.resource_type_name}
                        ]}},
                "permissions_mapping": [f"Resource1 : {Permission.READ.value} <-> Resource2 : {Permission.READ.value}"]
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
                    ServiceTHREDDS.service_type: {
                        "Resource1": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "{dir1_var}", "type": Directory.resource_type_name},
                            {"name": "{dir2_var}", "type": Directory.resource_type_name}],
                        "Resource2": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "{dir1_var}", "type": Directory.resource_type_name},
                            {"name": "dir2", "type": Directory.resource_type_name}
                        ]}},
                "permissions_mapping": [f"Resource1 : {Permission.READ.value} -> Resource2 : {Permission.READ.value}"]
            }
        }
        check_config(self.data)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            [f"Resource2 : {Permission.READ.value} -> Resource1 : {Permission.READ.value}"]
        check_config(self.data, ConfigErrorInvalidTokens)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            [f"Resource1 : {Permission.READ.value} <- Resource2 : {Permission.READ.value}"]
        check_config(self.data, ConfigErrorInvalidTokens)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            [f"Resource2 : {Permission.READ.value} <- Resource1 : {Permission.READ.value}"]
        check_config(self.data)

    def test_cross_service_mappings(self):
        """
        Tests config that uses mappings between permissions of different services.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    ServiceTHREDDS.service_type: {
                        "ThreddsMultiTokenResource": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name}],
                        "ThreddsNamedTokenResource": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "{dir1_var}", "type": Directory.resource_type_name},
                            {"name": "{dir2_var}", "type": Directory.resource_type_name}
                        ]},
                    ServiceGeoserver.service_type: {
                        "GeoserverMultiTokenResource": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": MULTI_TOKEN, "type": Directory.resource_type_name},
                            {"name": "file", "type": File.resource_type_name}],
                        "GeoserverUntokenizedResource": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "file", "type": File.resource_type_name}],
                        "GeoserverNamedTokenResource1": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "{dir1_var}", "type": Directory.resource_type_name},
                            {"name": "dir2", "type": Directory.resource_type_name}],
                        "GeoserverNamedTokenResource2": [
                            {"name": "catalog", "type": Service.resource_type_name},
                            {"name": "{dir1_var}", "type": Directory.resource_type_name},
                            {"name": "{dir2_var}", "type": Directory.resource_type_name}]
                    }},
                "permissions_mapping": [f"ThreddsMultiTokenResource : {Permission.READ.value} -> "
                                            f"GeoserverUntokenizedResource : {Permission.READ.value}",
                                        f"ThreddsMultiTokenResource : {Permission.READ.value} <-> "
                                            f"GeoserverMultiTokenResource : {Permission.READ.value}",
                                        f"ThreddsNamedTokenResource : {Permission.READ.value} -> "
                                            f"GeoserverUntokenizedResource : {Permission.READ.value}",
                                        f"ThreddsNamedTokenResource : {Permission.READ.value} -> "
                                            f"GeoserverNamedTokenResource1 : {Permission.READ.value}",
                                        f"ThreddsNamedTokenResource : {Permission.READ.value} <-> "
                                            f"GeoserverNamedTokenResource2 : {Permission.READ.value}"]
            }
        }
        check_config(self.data)
