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
from cowbird.services import ServiceFactory
from tests import utils


def create_test_service(data, url, cookies):
    """
    Creates a test service in Magpie app.
    """
    # Delete test service if already exists
    resp = utils.test_request(url, "GET", "/services/" + data["service_name"], cookies=cookies)
    if resp.status_code == 200:
        resp = utils.test_request(url, "DELETE", "/services/" + data["service_name"], cookies=cookies)
        utils.check_response_basic_info(resp, 200, expected_method="DELETE")
    else:
        utils.check_response_basic_info(resp, 404, expected_method="GET")

    # Create service
    resp = utils.test_request(url, "POST", "/services", cookies=cookies, json=data)
    body = utils.check_response_basic_info(resp, 201, expected_method="POST")
    return body['service']['resource_id']


def create_test_resource(data, url, cookies):
    """
    Creates a test resource in Magpie app.
    """
    resp = utils.test_request(url, "POST", "/resources", cookies=cookies, json=data)
    body = utils.check_response_basic_info(resp, 201, expected_method="POST")
    return body['resource']['resource_id']


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
        # Create test service
        data = {
            "service_name": cls.test_service_name,
            "service_type": "thredds",
            "service_sync_type": "thredds",
            "service_url": f"http://localhost:9000/{cls.test_service_name}",
            "configuration": {}
        }
        cls.test_service_id = create_test_service(data, cls.url, cls.cookies)

    def setUp(self):
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

    def test_webhooks_no_tokens(self):
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "Thredds": {
                        "Thredds1": [
                            {
                                "name": self.test_service_name,
                                "type": "service",
                            },
                            {
                                "name": "private",
                                "type": "directory"
                            },
                            {
                                "name": "workspace_file1",
                                "type": "file",
                            }
                        ],
                        "Thredds2": [
                            {
                                "name": self.test_service_name,
                                "type": "service",
                            },
                            {
                                "name": "workspace_file2",
                                "type": "file",
                            }
                        ]
                    }
                },
                "permissions_mapping": [
                    {
                        "Thredds1": ["read"],
                        "Thredds2": ["read"]
                    }
                ]
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        self.app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))
            # Create test resources
            test_resource_name = "private"
            data = {
              "resource_name": test_resource_name,
              "resource_display_name": test_resource_name,
              "resource_type": "directory",
              "parent_id": self.test_service_id
            }
            test_resource_id = create_test_resource(data, self.url, self.cookies)
            test_resource_name = "workspace_file1"
            data = {
              "resource_name": test_resource_name,
              "resource_display_name": test_resource_name,
              "resource_type": "file",
              "parent_id": test_resource_id
            }
            test_resource_id = create_test_resource(data, self.url, self.cookies)

            target_resource_name = "workspace_file2"
            data = {
              "resource_name": target_resource_name,
              "resource_display_name": target_resource_name,
              "resource_type": "directory",
              "parent_id": self.test_service_id
            }
            target_resource_id = create_test_resource(data, self.url, self.cookies)

            data = {
                "event": ValidOperations.CreateOperation.value,
                "service_name": "Thredds",
                "resource_id": str(test_resource_id),
                "resource_full_name": f"/{self.test_service_name}/{test_resource_name}",
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
            resp = utils.test_request(self.url, "GET", f"/users/{self.usr}/resources/{target_resource_id}/permissions",
                                      cookies=self.cookies)
            body = utils.check_response_basic_info(resp, 200, expected_method="GET")
            assert ["read", "read-allow-recursive"] == body["permission_names"]

            resp = utils.test_request(self.url, "GET", f"/groups/{self.grp}/resources/{target_resource_id}/permissions",
                                      cookies=self.cookies)
            body = utils.check_response_basic_info(resp, 200, expected_method="GET")
            assert ["read", "read-allow-recursive"] == body["permission_names"]

            # Delete permissions
            data["event"] = ValidOperations.DeleteOperation.value

            # Check if permissions were deleted
            resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")

            resp = utils.test_request(self.url, "GET", f"/users/{self.usr}/resources/{target_resource_id}/permissions",
                                      cookies=self.cookies)
            body = utils.check_response_basic_info(resp, 200, expected_method="GET")
            assert not body["permission_names"]

            resp = utils.test_request(self.url, "GET", f"/groups/{self.grp}/resources/{target_resource_id}/permissions",
                                      cookies=self.cookies)
            body = utils.check_response_basic_info(resp, 200, expected_method="GET")
            assert not body["permission_names"]
