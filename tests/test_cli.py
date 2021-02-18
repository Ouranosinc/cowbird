#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_cli
----------------------------------

Tests for :mod:`cowbird.cli` module.
"""
import subprocess

import pytest

from cowbird.cli import main as cowbird_cli
from tests.utils import TEST_INI_FILE

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
    out_lines = run_and_get_output("cowbird --help", trim=False)
    assert "usage: cowbird" in out_lines[0]
    idx = 0
    for idx, line in enumerate(out_lines):
        if "Helper:" in line:
            break
    cmd_lines = out_lines[idx:]
    assert all(any(helper in line for line in cmd_lines) for helper in KNOWN_HELPERS)


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
def test_cowbird_services_list_with_formats():
    out_lines = run_and_get_output("cowbird services list -f yaml -c '{}'".format(TEST_INI_FILE))
    assert out_lines[0] == "services:"
    out_lines = run_and_get_output("cowbird services list -f json -c '{}'".format(TEST_INI_FILE), trim=False)
    assert out_lines[0] == "{"
    assert '"services": [' in out_lines[1]  # pylint: disable=C4001
    out_lines = run_and_get_output("cowbird services list -f table -c '{}'".format(TEST_INI_FILE))
    assert "+---" in out_lines[0]
    assert "| services" in out_lines[1]
    assert "+===" in out_lines[2]
