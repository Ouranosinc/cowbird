#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_cli
----------------------------------

Tests for :mod:`cowbird.cli` module.
"""
import subprocess

import mock
import pytest

from cowbird.api.services.utils import Service
from cowbird.cli import main as cowbird_cli

KNOWN_HELPERS = [
    "services",
]


def run_and_get_output(command, trim=True):
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    proc = subprocess.Popen(command, shell=True, universal_newlines=True, stdout=subprocess.PIPE)  # nosec
    out, err = proc.communicate()
    assert not err, "process returned with error code {}".format(err)
    # when no output is present, it is either because CLI was not installed correctly, or caused by some other error
    assert out != "", "process did not execute as expected, no output available"
    out_lines = [line for line in out.splitlines() if not trim or (line and not line.startswith(" "))]
    assert len(out_lines), "could not retrieve any console output"
    return out_lines


@pytest.mark.cli
def test_cowbird_helper_help():
    out_lines = run_and_get_output("cowbird_helper --help", trim=False)
    assert "usage: cowbird_helper" in out_lines[0]
    assert all([helper in out_lines[1] for helper in KNOWN_HELPERS])


@pytest.mark.cli
def test_cowbird_helper_as_python():
    for helper in KNOWN_HELPERS:
        args = [helper, "--help"]
        try:
            cowbird_cli(args)
        except SystemExit as exc:
            assert exc.code == 0, "success output expected, non-zero or not None are errors"
        except Exception as exc:
            raise AssertionError("unexpected error raised instead of success exit code: [{!s}]".format(exc))
        else:
            raise AssertionError("expected exit code on help call not raised")


@pytest.mark.cli
def test_cowbird_services_list():
    def mocked_services(*_, **__):
        return [Service("unittest")]

    with mock.patch("cowbird.api.services.utils.get_services", side_effect=mocked_services):
        out_lines = run_and_get_output("cowbird services list --yaml")
    assert out_lines[0] == "services:"
    assert out_lines[1] == "  unittest"
