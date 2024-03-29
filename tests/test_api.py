#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_api
----------------------------------

Tests for :mod:`cowbird.api` module.
"""

import contextlib
import os
import tempfile
import unittest

import mock
import pytest
import yaml

from cowbird.handlers.handler_factory import HandlerFactory
from cowbird.utils import CONTENT_TYPE_JSON
from tests import utils


@pytest.mark.api
class TestAPI(unittest.TestCase):
    # pylint: disable=C0103,invalid-name
    """
    Test API operations of application.
    """

    @classmethod
    def setUpClass(cls):
        cls.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)  # pylint: disable=R1732
        with cls.cfg_file as f:
            f.write(yaml.safe_dump({"handlers": {"Magpie": {"active": True}}}))
        cls.app = utils.get_test_app(settings={"cowbird.config_path": cls.cfg_file.name})

    @classmethod
    def tearDownClass(cls):
        utils.clear_handlers_instances()
        os.unlink(cls.cfg_file.name)

    def test_homepage(self):
        resp = utils.test_request(self.app, "GET", "/")
        body = utils.check_response_basic_info(resp)
        utils.check_val_is_in("name", body)
        utils.check_val_is_in("title", body)
        utils.check_val_is_in("contact", body)
        utils.check_val_is_in("description", body)
        utils.check_val_is_in("documentation", body)
        utils.check_val_is_in("cowbird", body["name"])

    def test_webhooks(self):
        """
        Test that sends a webhook request from Magpie to cowbird.
        """
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.handlers.impl.magpie.Magpie",
                                           side_effect=utils.MockMagpieHandler))
            data = {
                "event": "created",
                "user_name": "test_user",
                "callback_url": "http://magpie.domain.ca/tmp/109e1d0d-e27c-4601-9d45-984c9b61ebff"
            }
            resp = utils.test_request(self.app, "POST", "/webhooks/users", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            utils.check_response_basic_info(resp)
            magpie = HandlerFactory().get_handler("Magpie")
            assert len(magpie.json()["event_users"]) == 1
            assert magpie.json()["event_users"][0] == data["user_name"]

            data["event"] = "deleted"
            data.pop("callback_url")
            resp = utils.test_request(self.app, "POST", "/webhooks/users", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            assert len(magpie.json()["event_users"]) == 0

            data = {
                "event": "created",
                "service_name": "string",
                "service_type": "string",
                "resource_id": 1,
                "resource_full_name": "thredds/birdhouse/file.nc",
                "name": "read",
                "access": "allow",
                "scope": "recursive",
                "user": "string",
                "group": "string"
            }
            resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            magpie = HandlerFactory().get_handler("Magpie")
            assert len(magpie.json()["event_perms"]) == 1
            assert magpie.json()["event_perms"][0] == data["resource_full_name"]

            data["event"] = "deleted"
            resp = utils.test_request(self.app, "POST", "/webhooks/permissions", json=data)
            utils.check_response_basic_info(resp, 200, expected_method="POST")
            assert len(magpie.json()["event_perms"]) == 0


@pytest.mark.api
def test_response_metadata():
    """
    Validate that regardless of response type (success/error) and status-code, metadata details are added.

    note: test only locally to avoid remote server side-effects and because mock cannot be done remotely
    """

    class MockHandler(object):
        def name(self):
            raise TypeError()

    app = utils.get_test_app()
    # all paths below must be publicly accessible
    for i, (code, method, path, kwargs) in enumerate([
        (200, "GET", "", {}),
        (400, "GET", "/handlers/!!!!", {}),  # invalid format
        # (401, "GET", "/handlers", {}),  # anonymous unauthorized
        (404, "GET", "/random", {}),
        (405, "POST", "/json", {"body": {}}),
        (406, "GET", "/api", {"headers": {"Accept": "application/pdf"}}),
        # 409: need connection to test conflict, no route available without so (other tests validates them though)
        # (422, "POST", "/handlers", {"body": {"name": 1}}),  # invalid field type  # FIXME: route impl required
        (500, "GET", "/handlers", {}),  # see mock
    ], start=1):
        with contextlib.ExitStack() as stack:
            if code == 500:
                stack.enter_context(mock.patch("cowbird.handlers.impl.magpie.Magpie", side_effect=MockHandler))
            headers = {"Accept": CONTENT_TYPE_JSON, "Content-Type": CONTENT_TYPE_JSON}
            headers.update(kwargs.get("headers", {}))
            kwargs.pop("headers", None)
            resp = utils.test_request(app, method, path, expect_errors=True, headers=headers, **kwargs)
            # following util check validates all expected request metadata in response body
            msg = f"\n[Test: #{i}, Code: {code}]"
            utils.check_response_basic_info(resp, expected_code=code, expected_method=method, extra_message=msg)


if __name__ == "__main__":
    import sys
    sys.exit(unittest.main())
