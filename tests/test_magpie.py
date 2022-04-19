#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
These tests require a working Magpie instance.

They are ignored by the CI, but are
still useful for a developer working on the Magpie requests. They can be run with the `Make test-magpie` target.
"""

import contextlib
import os
import requests
import tempfile
import unittest

import mock
import pytest
import yaml

from cowbird.api.schemas import ValidOperations
from cowbird.config import MULTI_TOKEN, SINGLE_TOKEN
from cowbird.services import ServiceFactory
from tests import utils


@pytest.mark.online
@pytest.mark.magpie
class TestMagpieRequests(unittest.TestCase):
    """
    Test Magpie operations of application.
    """

    @classmethod
    def setUpClass(cls):
        cls.grp = "administrators"
        cls.usr = "admin"
        cls.pwd = "qwertyqwerty"
        cls.url = "http://localhost:2001/magpie"

        data = {"user_name": cls.usr, "password": cls.pwd,
                "provider_name": "ziggurat"}  # ziggurat = magpie_default_provider
        resp = requests.post("{}/signin".format(cls.url), json=data)
        utils.check_response_basic_info(resp, 200, expected_method="POST")
        cls.cookies = resp.cookies

        cls.test_service_name = "catalog"

    def setUp(self):
        # Create test service
        self.test_service_id = self.reset_test_service()

        self.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)
        self.data = {"services": {
                "Magpie": {
                    "active": True,
                    "url": "http://localhost:2001/magpie"
                },
                "Thredds": {"active": True}
            }
        }

    def tearDown(self):
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
        return body['service']['resource_id']

    def delete_test_service(self):
        # Delete test service if it exists
        resp = utils.test_request(self.url, "GET", "/services/" + self.test_service_name, cookies=self.cookies)
        if resp.status_code == 200:
            resp = utils.test_request(self.url, "DELETE", "/services/" + self.test_service_name, cookies=self.cookies)
            utils.check_response_basic_info(resp, 200, expected_method="DELETE")
        else:
            utils.check_response_basic_info(resp, 404, expected_method="GET")

    def create_test_resource(self, resource_name, resource_type, parent_id):
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
        return body['resource']['resource_id']

    def check_user_permissions(self, resource_id, expected_permissions):
        resp = utils.test_request(self.url, "GET", f"/users/{self.usr}/resources/{resource_id}/permissions",
                                  cookies=self.cookies)
        body = utils.check_response_basic_info(resp, 200, expected_method="GET")
        assert body["permission_names"] == expected_permissions

    def check_group_permissions(self, resource_id, expected_permissions):
        resp = utils.test_request(self.url, "GET", f"/groups/{self.grp}/resources/{resource_id}/permissions",
                                  cookies=self.cookies)
        body = utils.check_response_basic_info(resp, 200, expected_method="GET")
        assert body["permission_names"] == expected_permissions

    def test_webhooks_no_tokens(self):
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "Thredds": {
                        "Thredds1": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "private", "type": "directory"},
                            {"name": "workspace_file1", "type": "file"}],
                        "Thredds2": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "workspace_file2", "type": "file"}]}},
                "permissions_mapping": [
                    {"Thredds1": ["read"], "Thredds2": ["read"]}]
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        self.app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie service instance with new config
        ServiceFactory().create_service("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))
            # Create test resources
            parent_res_id = self.create_test_resource("private", "directory", self.test_service_id)
            src_res_id = self.create_test_resource("workspace_file1", "file", parent_res_id)
            target_res_id = self.create_test_resource("workspace_file2", "directory", self.test_service_id)

            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": "Thredds",
                "resource_id": str(src_res_id),
                "resource_full_name": f"/{self.test_service_name}/private/workspace_file1",
                "name": "read",
                "access": "allow",
                "scope": "recursive",
                "user": self.usr,
                "group": self.grp
            }

            # Create permissions
            resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")

            # Check if permissions were created
            self.check_user_permissions(target_res_id, ["read", "read-allow-recursive"])
            self.check_group_permissions(target_res_id, ["read", "read-allow-recursive"])

            # Delete permissions
            data["event"] = ValidOperations.DeleteOperation.value
            resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")

            # Check if permissions were deleted
            self.check_user_permissions(target_res_id, [])
            self.check_group_permissions(target_res_id, [])

    def test_webhooks_valid_tokens(self):
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "Thredds": {
                        "Thredds_file_src": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "private", "type": "directory"},
                            {"name": MULTI_TOKEN, "type": "directory"},
                            {"name": SINGLE_TOKEN, "type": "file"}],
                        "Thredds_file_target": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"},
                            {"name": SINGLE_TOKEN, "type": "file"}],
                        "Thredds_dir_src": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "private", "type": "directory"},
                            {"name": MULTI_TOKEN, "type": "directory"}],
                        "Thredds_dir_target": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}]}},
                "permissions_mapping": [
                    {"Thredds_file_src": ["read"], "Thredds_file_target": ["read"]},
                    {"Thredds_dir_src": ["read"], "Thredds_dir_target": ["read"]}]
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        self.app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie service instance with new config
        ServiceFactory().create_service("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))

            # Create test resources
            src1_res_id = self.create_test_resource("private", "directory", self.test_service_id)
            parent_res_id = self.create_test_resource("dir1", "directory", src1_res_id)
            parent_res_id = self.create_test_resource("dir2", "directory", parent_res_id)
            src2_res_id = self.create_test_resource("workspace_file", "file", parent_res_id)

            target1_res_id = self.test_service_id
            parent_res_id = self.create_test_resource("dir1", "directory", self.test_service_id)
            parent_res_id = self.create_test_resource("dir2", "directory", parent_res_id)
            target2_res_id = self.create_test_resource("workspace_file", "file", parent_res_id)

            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": "Thredds",
                "resource_id": str(src1_res_id),
                "resource_full_name": f"/{self.test_service_name}/private",
                "name": "read",
                "access": "allow",
                "scope": "recursive",
                "user": self.usr,
                "group": None
            }

            # Create permissions
            resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")

            # Check if only corresponding permissions were created
            self.check_user_permissions(target1_res_id, ["read", "read-allow-recursive"])
            self.check_user_permissions(target2_res_id, [])

            # Create and check permissions on other resource
            data["resource_id"] = str(src2_res_id)
            data["resource_full_name"] = f"/{self.test_service_name}/private/dir1/dir2/workspace_file"

            resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            self.check_user_permissions(target2_res_id, ["read", "read-allow-recursive"])

    def test_webhooks_tokens_invalid_suffix(self):
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "Thredds": {
                        "Thredds_src": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": "private", "type": "directory"},
                            {"name": SINGLE_TOKEN, "type": "directory"},
                            {"name": SINGLE_TOKEN, "type": "file"}],
                        "Thredds_target": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": SINGLE_TOKEN, "type": "directory"}]}},
                "permissions_mapping": [
                    {"Thredds_src": ["read"], "Thredds_target": ["read"]}]
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        self.app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie service instance with new config
        ServiceFactory().create_service("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))
            # Create test resources
            parent_res_id = self.create_test_resource("private", "directory", self.test_service_id)
            parent_res_id = self.create_test_resource("dir1", "directory", parent_res_id)
            src_res_id = self.create_test_resource("workspace_file", "file", parent_res_id)

            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": "Thredds",
                "resource_id": str(src_res_id),
                "resource_full_name": f"/{self.test_service_name}/private/dir1/workspace_file",
                "name": "read",
                "access": "allow",
                "scope": "recursive",
                "user": self.usr,
                "group": None
            }

            # Try creating permissions
            resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data, expect_errors=True)
            # Should create an error since resource tokenized `suffix` will not fit with the target resource path
            utils.check_response_basic_info(resp, 500, expected_method="POST")

    def test_webhooks_invalid_multimatch(self):
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "Thredds": {
                        "Thredds_match1": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": SINGLE_TOKEN, "type": "directory"}],
                        "Thredds_match2": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}]}},
                "permissions_mapping": [
                    {"Thredds_match1": ["read"], "Thredds_match2": ["read"]}]
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        self.app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie service instance with new config
        ServiceFactory().create_service("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))
            # Create test resources
            src_res_id = self.create_test_resource("dir", "directory", self.test_service_id)

            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": "Thredds",
                "resource_id": str(src_res_id),
                "resource_full_name": f"/{self.test_service_name}/dir",
                "name": "read",
                "access": "allow",
                "scope": "recursive",
                "user": self.usr,
                "group": None
            }

            # Try creating permissions
            resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data, expect_errors=True)
            # Should create an error since input resource to synchronize can match with both resources in config
            utils.check_response_basic_info(resp, 500, expected_method="POST")

    def test_webhooks_no_match(self):
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "Thredds": {
                        "Thredds1": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": SINGLE_TOKEN, "type": "directory"}],
                        "Thredds2": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}]}},
                "permissions_mapping": [
                    {"Thredds1": ["read"], "Thredds2": ["read"]}]
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        self.app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie service instance with new config
        ServiceFactory().create_service("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))
            # Create test resources
            src_res_id = self.create_test_resource("dir", "file", self.test_service_id)

            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": "Thredds",
                "resource_id": str(src_res_id),
                "resource_full_name": f"/{self.test_service_name}/dir",
                "name": "read",
                "access": "allow",
                "scope": "recursive",
                "user": self.usr,
                "group": None
            }

            # Try creating permissions
            resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data, expect_errors=True)
            # Should create an error since input resource doesn't match the type of resources found in config
            utils.check_response_basic_info(resp, 500, expected_method="POST")

    def test_webhooks_invalid_service(self):
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "Thredds": {
                        "Thredds1": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": SINGLE_TOKEN, "type": "directory"}]},
                    "Invalid_Service": {
                        "Invalid": [
                            {"name": self.test_service_name, "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}]}},
                "permissions_mapping": [
                    {"Thredds1": ["read"], "Invalid": ["read"]}]
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        self.app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Recreate new magpie service instance with new config
        ServiceFactory().create_service("Magpie")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))
            # Create test resources
            src_res_id = self.create_test_resource("dir", "directory", self.test_service_id)

            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": "Thredds",
                "resource_id": str(src_res_id),
                "resource_full_name": f"/{self.test_service_name}/dir",
                "name": "read",
                "access": "allow",
                "scope": "recursive",
                "user": self.usr,
                "group": None
            }

            # Try creating permissions
            resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
            # Should not create an error, the invalid service should be ignored when reading the config
            # It should have done nothing since no permissions to synchronize are found.
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            # Check that only the valid service was included in the sync_point
            magpie = ServiceFactory().get_service("Magpie")
            assert len(magpie.permissions_synch.sync_point) == 1
            assert len(magpie.permissions_synch.sync_point[0].services) == 1
