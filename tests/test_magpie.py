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
        cls.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)
        with cls.cfg_file as f:
            f.write(yaml.safe_dump({"services": {
                "Magpie": {
                    "active": True,
                    "url": "http://localhost:2001/magpie"
                },
                "Thredds": {"active": True}
            },
                "sync_permissions": {
                    "user_workspace": {
                        "services": {
                            "Thredds": {
                                "Catalog": [
                                    {
                                        "name": "catalog",
                                        "type": "service",
                                    }
                                ],
                                "Thredds1": [
                                    {
                                        "name": "catalog",
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
                                        "name": "catalog",
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
            }))

        cls.app = utils.get_test_app(settings={"cowbird.config_path": cls.cfg_file.name})

        cls.grp = "administrators"
        cls.usr = "admin"
        cls.pwd = "qwertyqwerty"
        cls.url = "http://localhost:2001/magpie"

        data = {"user_name": cls.usr, "password": cls.pwd,
                "provider_name": "ziggurat"}  # ziggurat = magpie_default_provider
        resp = requests.post("{}/signin".format(cls.url), json=data)
        utils.check_response_basic_info(resp, 200, expected_method="POST")
        cls.cookies = resp.cookies

    @classmethod
    def tearDownClass(cls):
       # utils.clear_services_instances()
        os.unlink(cls.cfg_file.name)

    def test_webhooks(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))

            test_service_name = "catalog"
            # Create test service
            data = {
                "service_name": test_service_name,
                "service_type": "thredds",
                "service_sync_type": "thredds",
                "service_url": f"http://localhost:9000/{test_service_name}",
                "configuration": {}
            }
            test_service_id = create_test_service(data, self.url, self.cookies)

            # Create test resource
            test_resource_name = "private"
            data = {
              "resource_name": test_resource_name,
              "resource_display_name": test_resource_name,
              "resource_type": "directory",
              "parent_id": test_service_id
            }
            test_resource_id = create_test_resource(data, self.url, self.cookies)

            # Create test resource
            test_resource_name = "workspace_file1"
            data = {
              "resource_name": test_resource_name,
              "resource_display_name": test_resource_name,
              "resource_type": "file",
              "parent_id": test_resource_id
            }
            test_resource_id = create_test_resource(data, self.url, self.cookies)

            # # Create the resource which should be synced to the above resource
            # synced_resource_name = "workspaces2"
            # data = {
            #   "resource_name": synced_resource_name,
            #   "resource_display_name": synced_resource_name,
            #   "resource_type": "directory",
            #   "parent_id": test_service_id
            # }
            # synced_resource_id = create_test_resource(data, self.url, self.cookies)

            resp = utils.test_request(self.url, "GET", "/resources", cookies=self.cookies)
            body = utils.check_response_basic_info(resp, 200, expected_method="GET")
            print(body)

            data = {
                "event": "created",
                "service_name": "Thredds",
                "resource_id": str(test_resource_id),
                "resource_full_name": f"/{test_service_name}/{test_resource_name}",
                "name": "read",
                "access": "allow",
                "scope": "recursive",
                "user": self.usr,
                "group": None  # TODO: do other test request using the group
            }
            resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")

            magpie = ServiceFactory().get_service("Magpie")
            #assert len(magpie.json()["event_perms"]) == 1
            #assert magpie.json()["event_perms"][0] == data["resource_full_name"]

            # # test POST PERMISSION
            # data = {
            #     "permission_name": "read", # read, browse, ...
            #     "permission": {
            #         "name": "read",
            #         "access": "allow",
            #         "scope": "recursive"
            #     }
            # }
            # resp = utils.test_request(self.url, "POST", f"/users/{self.usr}/resources/{resource_id}/permissions",
            #                           json=data, cookies=self.cookies)
            # body = utils.check_response_basic_info(resp, 201, expected_method="POST")
            # print(body)

            # TODO: supprimer le test service/resource
            # TODO: test pour delete_permission
