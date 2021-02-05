#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_api
----------------------------------

Tests for :mod:`cowbird.api` module.
"""

import unittest

import mock
import pytest

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
        cls.app = utils.get_test_app()

    def test_homepage(self):
        app = utils.get_test_app()
        resp = utils.test_request(app, "GET", "/")
        body = utils.check_response_basic_info(resp)
        utils.check_val_is_in("name", body)
        utils.check_val_is_in("title", body)
        utils.check_val_is_in("contact", body)
        utils.check_val_is_in("description", body)
        utils.check_val_is_in("documentation", body)
        utils.check_val_is_in("cowbird", body["name"])


@pytest.mark.api
def test_response_metadata():
    """
    Validate that regardless of response type (success/error) and status-code, metadata details are added.

    note: test only locally to avoid remote server side-effects and because mock cannot be done remotely
    """

    def raise_request(*_, **__):
        raise TypeError()

    app = utils.get_test_app()
    # all paths below must be publicly accessible
    for code, method, path, kwargs in [
        (200, "GET", "", {}),
        # FIXME: sort out 400 vs 422 everywhere (https://github.com/Ouranosinc/cowbird/issues/359)
        # (400, "POST", "/signin", {"body": {}}),  # missing credentials
        # (401, "GET", "/services", {}),  # anonymous unauthorized
        (404, "GET", "/random", {}),
        (405, "POST", "/api", {"body": {}}),
        (406, "GET", "/api", {"headers": {"Accept": "application/pdf"}}),
        # 409: need connection to test conflict, no route available without so (other tests validates them though)
        (422, "POST", "/signin", {"body": {"user_name": "!!!!"}}),  # invalid format
        (500, "GET", "/services", {}),  # see mock
    ]:
        with mock.patch("cowbird.api.services.utils.get_services", side_effect=raise_request):
            headers = {"Accept": CONTENT_TYPE_JSON, "Content-Type": CONTENT_TYPE_JSON}
            headers.update(kwargs.get("headers", {}))
            kwargs.pop("headers", None)
            resp = utils.test_request(app, method, path, expect_errors=True, headers=headers, **kwargs)
            # following util check validates all expected request metadata in response body
            utils.check_response_basic_info(resp, expected_code=code, expected_method=method)


if __name__ == "__main__":
    import sys
    sys.exit(unittest.main())
