#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_utils
----------------------------------

Tests for the various utility operations.
"""

import unittest

import mock
import pytest
from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden, HTTPInternalServerError, HTTPOk
from pyramid.settings import asbool

from cowbird import __meta__
from cowbird.api import exception as ax
from cowbird.api import generic as ag
from cowbird.api import requests as ar
from cowbird.utils import CONTENT_TYPE_JSON, ExtendedEnum, get_header
from tests import utils


class DummyEnum(ExtendedEnum):
    VALUE1 = "value-1"
    VALUE2 = "value-2"


@pytest.mark.utils
class TestUtils(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.version = __meta__.__version__  # only local test

    def test_get_header_split(self):
        headers = {"Content-Type": "{}; charset=UTF-8".format(CONTENT_TYPE_JSON)}
        for name in ["content_type", "content-type", "Content_Type", "Content-Type", "CONTENT_TYPE", "CONTENT-TYPE"]:
            for split in [";,", ",;", ";", (",", ";"), [";", ","]]:
                utils.check_val_equal(get_header(name, headers, split=split), CONTENT_TYPE_JSON)

    def test_get_query_param(self):
        resp = utils.mock_request("/some/path")
        v = ar.get_query_param(resp, "value")
        utils.check_val_equal(v, None)

        resp = utils.mock_request("/some/path?other=test")
        v = ar.get_query_param(resp, "value")
        utils.check_val_equal(v, None)

        resp = utils.mock_request("/some/path?other=test")
        v = ar.get_query_param(resp, "value", True)
        utils.check_val_equal(v, True)

        resp = utils.mock_request("/some/path?value=test")
        v = ar.get_query_param(resp, "value", True)
        utils.check_val_equal(v, "test")

        resp = utils.mock_request("/some/path?query=value")
        v = ar.get_query_param(resp, "query")
        utils.check_val_equal(v, "value")

        resp = utils.mock_request("/some/path?QUERY=VALUE")
        v = ar.get_query_param(resp, "query")
        utils.check_val_equal(v, "VALUE")

        resp = utils.mock_request("/some/path?QUERY=VALUE")
        v = asbool(ar.get_query_param(resp, "query"))
        utils.check_val_equal(v, False)

        resp = utils.mock_request("/some/path?Query=TRUE")
        v = asbool(ar.get_query_param(resp, "query"))
        utils.check_val_equal(v, True)

    def test_verify_param_proper_verifications_raised(self):
        # with default error
        utils.check_raises(lambda: ax.verify_param("b", param_compare=["a", "b"], not_in=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param("x", param_compare=["a", "b"], is_in=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param("1", param_compare=int, is_type=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param(1.0, param_compare=str, is_type=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param("x", param_compare="x", not_equal=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param("x", param_compare="y", is_equal=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param(False, is_true=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param(True, is_false=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param(None, not_none=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param(1, is_none=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param("", not_empty=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param("abc", is_empty=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param("abc", matches=True, param_compare=r"[A-Z]+"), HTTPBadRequest)

        # with requested error
        utils.check_raises(lambda:
                           ax.verify_param("b", param_compare=["a", "b"], not_in=True, http_error=HTTPForbidden),
                           HTTPForbidden)
        utils.check_raises(lambda: ax.verify_param("x", param_compare=["a", "b"], is_in=True, http_error=HTTPForbidden),
                           HTTPForbidden)
        utils.check_raises(lambda: ax.verify_param("1", param_compare=int, is_type=True, http_error=HTTPForbidden),
                           HTTPForbidden)
        utils.check_raises(lambda: ax.verify_param("x", param_compare="x", not_equal=True, http_error=HTTPForbidden),
                           HTTPForbidden)
        utils.check_raises(lambda: ax.verify_param("x", param_compare="y", is_equal=True, http_error=HTTPForbidden),
                           HTTPForbidden)
        utils.check_raises(lambda: ax.verify_param(False, is_true=True, http_error=HTTPForbidden), HTTPForbidden)
        utils.check_raises(lambda: ax.verify_param(True, is_false=True, http_error=HTTPForbidden), HTTPForbidden)
        utils.check_raises(lambda: ax.verify_param(None, not_none=True, http_error=HTTPForbidden), HTTPForbidden)
        utils.check_raises(lambda: ax.verify_param(1, is_none=True, http_error=HTTPForbidden), HTTPForbidden)
        utils.check_raises(lambda: ax.verify_param("", not_empty=True, http_error=HTTPForbidden), HTTPForbidden)
        utils.check_raises(lambda: ax.verify_param("abc", is_empty=True, http_error=HTTPForbidden), HTTPForbidden)
        utils.check_raises(lambda:
                           ax.verify_param("abc", matches=True, param_compare=r"[A-Z]+", http_error=HTTPForbidden),
                           HTTPForbidden)

    def test_verify_param_proper_verifications_passed(self):
        ax.verify_param("x", param_compare=["a", "b"], not_in=True)
        ax.verify_param("b", param_compare=["a", "b"], is_in=True)
        ax.verify_param(1, param_compare=int, is_type=True)
        ax.verify_param("x", param_compare=str, is_type=True)
        ax.verify_param("x", param_compare=str, is_type=True)
        ax.verify_param("x", param_compare="y", not_equal=True)
        ax.verify_param("x", param_compare="x", is_equal=True)
        ax.verify_param(True, is_true=True)
        ax.verify_param(False, is_false=True)
        ax.verify_param(1, not_none=True)
        ax.verify_param(None, is_none=True)
        ax.verify_param("abc", not_empty=True)
        ax.verify_param("", is_empty=True)
        ax.verify_param("abc", matches=True, param_compare=r"[a-z]+")

    def test_verify_param_args_incorrect_usage(self):
        """
        Invalid usage of function raises internal server error instead of 'normal HTTP error'.
        """
        utils.check_raises(lambda: ax.verify_param("b", param_compare=["a", "b"]),
                           HTTPInternalServerError, msg="missing any flag specification should be caught")
        utils.check_raises(lambda: ax.verify_param("b", param_compare=["a", "b"], not_in=None),  # noqa
                           HTTPInternalServerError, msg="flag specified with incorrect type should be caught")
        utils.check_raises(lambda: ax.verify_param("b", not_in=True),
                           HTTPInternalServerError, msg="missing 'param_compare' for flag needing it should be caught")
        utils.check_raises(lambda: ax.verify_param("b", param_compare=["b"], not_in=True, http_error=HTTPOk),  # noqa
                           HTTPInternalServerError, msg="incorrect HTTP class to raise error should be caught")
        utils.check_raises(lambda: ax.verify_param([1], param_compare=1, is_in=True),
                           HTTPInternalServerError, msg="incorrect non-iterable compare should raise invalid type")
        for flag in ["not_none", "not_empty", "not_in", "not_equal", "is_none", "is_empty", "is_in", "is_equal",
                     "is_true", "is_false", "is_type", "matches"]:
            utils.check_raises(lambda: ax.verify_param("x", **{flag: 1}),
                               HTTPInternalServerError, msg="invalid flag '{}' type should be caught".format(flag))

    def test_verify_param_compare_types(self):
        """
        Arguments ``param`` and ``param_compare`` must be of same type for valid comparison, except for ``is_type``
        where compare parameter must be the type directly.

        .. versionchanged:: 2.0

            Since ``param`` can come from user input, we should **NOT** raise ``HTTPInternalServerError`` because the
            whole point of the method is to ensure that values are compared accordingly in a controlled fashion.
            Therefore, error to be raised is an 'expected' validation failure (``HTTPBadRequest`` or whichever
            ``http_error`` provided) instead of runtime 'unexpected' processing error.

            On the other hand, when ``is_type`` flag is requested, we know that ``param_compare`` must be a type.
            Inversely, ``param_compare`` must not be a type if ``is_type`` is not requested, but other flags require
            some form of comparison between values. We evaluate these use cases here.

        .. seealso::
            - :func:`test_verify_param_args_incorrect_usage` for invalid input use-cases
        """
        # compare flags expecting a value (can only consider it bad request because comparison values are valid)
        utils.check_raises(lambda: ax.verify_param("1", param_compare=1, is_equal=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param("1", param_compare=True, is_equal=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param(1, param_compare="1", is_equal=True), HTTPBadRequest)
        utils.check_raises(lambda: ax.verify_param(1, param_compare=True, is_equal=True), HTTPBadRequest)
        # when compare flags expect a value but type is provided, should still detect incorrect input
        utils.check_raises(lambda: ax.verify_param(1, param_compare=int, is_equal=True), HTTPInternalServerError)
        utils.check_raises(lambda: ax.verify_param("1", param_compare=str, is_equal=True), HTTPInternalServerError)

        # compare flags expecting param_compare to be a type while value provided is not
        utils.check_raises(lambda: ax.verify_param(1, param_compare="x", is_type=True), HTTPInternalServerError)
        utils.check_raises(lambda: ax.verify_param(1, param_compare=True, is_type=True), HTTPInternalServerError)
        utils.check_raises(lambda: ax.verify_param("1", param_compare=None, is_type=True), HTTPInternalServerError)

        # compare flags expecting param_compare to be some container instance while value provided is not
        utils.check_raises(lambda: ax.verify_param(1, param_compare=1, is_in=True), HTTPInternalServerError)
        utils.check_raises(lambda: ax.verify_param(1, param_compare=list, is_in=True), HTTPInternalServerError)
        utils.check_raises(lambda: ax.verify_param("1", param_compare=str, is_in=True), HTTPInternalServerError)
        utils.check_raises(lambda: ax.verify_param(1, param_compare=1, not_in=True), HTTPInternalServerError)
        utils.check_raises(lambda: ax.verify_param(1, param_compare=list, not_in=True), HTTPInternalServerError)
        utils.check_raises(lambda: ax.verify_param("1", param_compare=str, not_in=True), HTTPInternalServerError)

        # strings cases handled correctly (no raise)
        utils.check_no_raise(lambda: ax.verify_param("1", param_compare="1", is_equal=True))

    def test_enum_values_listing(self):
        utils.check_all_equal(DummyEnum.values(), ["value-1", "value-2"], any_order=True)

    def test_enum_get_by_value(self):
        utils.check_val_equal(DummyEnum.get("value-1"), DummyEnum.VALUE1)
        utils.check_val_equal(DummyEnum.get("VALUE1"), DummyEnum.VALUE1)
        utils.check_val_equal(DummyEnum.get("random"), None)
        utils.check_val_equal(DummyEnum.get("random", "something"), "something")

    def test_enum_other(self):
        class OtherEnum(ExtendedEnum):
            VALUE1 = DummyEnum.VALUE1.value  # copy internal string representation

        utils.check_val_not_equal(DummyEnum.VALUE1, OtherEnum.VALUE1, msg="concrete enum elements should be different")

    def test_evaluate_call_callable_incorrect_usage(self):
        """
        Verifies that incorrect usage of utility is raised accordingly.
        """
        utils.check_raises(lambda: ax.evaluate_call(int),
                           HTTPInternalServerError, msg="invalid callable non-lambda 'call' should raise")
        utils.check_raises(lambda: ax.evaluate_call(lambda: int, fallback=int),  # noqa
                           HTTPInternalServerError, msg="invalid callable non-lambda 'fallback' should raise")

    def test_evaluate_call_recursive_safeguard(self):
        """
        Validate use case if internal function that handles formatting and generation of a resulting HTTP response
        raises itself an error (because of implementation issue), while it is processing another pre-raised error, that
        it does not end up into an endless recursive call stack of raised errors.
        """
        mock_calls = {"counter": 0}

        def mock_raise(*_, **__):
            # avoid raising forever if the real safeguard fails doing its job
            if mock_calls["counter"] >= 2 * ax.RAISE_RECURSIVE_SAFEGUARD_MAX:
                return TypeError()
            mock_calls["counter"] += 1
            raise TypeError()

        def mock_lambda_call(*_, **__):
            ax.evaluate_call(lambda: int("x"))

        try:
            app = utils.get_test_app()
            with mock.patch("cowbird.api.exception.generate_response_http_format", side_effect=mock_raise):
                with mock.patch("cowbird.api.services.views.get_services", side_effect=mock_lambda_call):
                    # Call request that ends up calling the response formatter via 'evaluate_call' itself raising to
                    # trigger 'mock_raise' recursively within 'raise_http' function.
                    # Since tweens are set up to format all response prior to return, the raised error will itself
                    # call 'raise_http' again each time operation fails, creating recursive raises.
                    # If recursive safeguard does its job, it should end up raising 'HTTPInternalServerError' directly
                    # (without further formatting attempt when reaching the MAX value), stopping the endless loop.
                    utils.test_request(app, "GET", "/services", expect_errors=True)
        except AssertionError:
            # Request called with above 'test_request' should catch the final 'HTTPInternalServerError' that is
            # raised directly instead of usual TestResponse returned. That error is again re-raised as 'AssertionError'
            pass
        except Exception as exc:
            self.fail("unexpected error during request creation should not raise: {}".format(exc))

        # if our counter reached higher than the MAX (i.e.: 2*MAX from mock), the safeguard did not do its job
        # if it did not get called at least more than once, use cases did not really get tested
        utils.check_val_is_in(mock_calls["counter"], list(range(2, ax.RAISE_RECURSIVE_SAFEGUARD_MAX + 1)))  # noqa

    def test_format_content_json_str_invalid_usage(self):
        non_json_serializable_content = {"key": HTTPInternalServerError()}
        utils.check_raises(
            lambda: ax.format_content_json_str(200, "", non_json_serializable_content, CONTENT_TYPE_JSON),
            HTTPInternalServerError, msg="invalid content format expected as JSON serializable should raise"
        )

    def test_generate_response_http_format_invalid_usage(self):
        utils.check_raises(
            lambda: ax.generate_response_http_format(None, {}, {}, "", {}),  # noqa
            HTTPInternalServerError, msg="invalid arguments resulting in error during response generation should raise"
        )

    def test_guess_target_format_default(self):
        request = utils.mock_request()
        content_type, where = ag.guess_target_format(request)
        utils.check_val_equal(content_type, CONTENT_TYPE_JSON)
        utils.check_val_equal(where, True)
