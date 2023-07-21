#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_cli
----------------------------------

Tests for :mod:`cowbird.cli` module.
"""
import contextlib
import subprocess
from io import StringIO
from pathlib import Path

import mock
import pytest

from cowbird.cli import main as cowbird_cli
from cowbird.config import get_all_configs
from tests.utils import TEST_CFG_FILE, TEST_INI_FILE, MockMagpieHandler

KNOWN_HELPERS = [
    "handlers",
]

CURR_DIR = Path(__file__).resolve().parent


def run_and_get_output(command, trim=True):
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    with subprocess.Popen(command, shell=True, universal_newlines=True, stdout=subprocess.PIPE) as proc:  # nosec
        out, err = proc.communicate()
    assert not err, f"process returned with error code {err}"
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
            raise AssertionError(f"unexpected error raised instead of success exit code: [{exc!s}]")
        else:
            raise AssertionError("expected exit code on help call not raised")


@pytest.mark.cli
def test_cowbird_handlers_list_with_formats():
    override = {"COWBIRD_CONFIG_PATH": TEST_CFG_FILE}
    handlers_config = get_all_configs(TEST_CFG_FILE, "handlers")[0]

    with mock.patch.dict("os.environ", override), contextlib.ExitStack() as stack:
        # Mocked Magpie required since config is validated when calling cli, and config validation relies
        # on a Magpie instance.
        stack.enter_context(mock.patch("cowbird.handlers.impl.magpie.Magpie", side_effect=MockMagpieHandler))

        f = StringIO()
        with contextlib.redirect_stdout(f):
            cowbird_cli(["handlers", "list", "-f", "yaml", "-c", TEST_INI_FILE])
        output_yaml = f.getvalue().split("\n")
        assert output_yaml[0] == "handlers:"

        f = StringIO()
        with contextlib.redirect_stdout(f):
            cowbird_cli(["handlers", "list", "-f", "json", "-c", TEST_INI_FILE])
        output_json = f.getvalue().split("\n")
        assert output_json[0] == "{"
        assert "\"handlers\": [" in output_json[1]

        f = StringIO()
        with contextlib.redirect_stdout(f):
            cowbird_cli(["handlers", "list", "-f", "table", "-c", TEST_INI_FILE])
        output_table = f.getvalue().split("\n")
        assert "+---" in output_table[0]
        assert "| handlers" in output_table[1]
        assert "+===" in output_table[2]

        # Test handlers config
        active_handlers = [line.strip("|").strip(" ") for line in output_table[3:-2]]
        # Every active handler should be in test data
        for handler in active_handlers:
            assert handler in handlers_config
            assert handlers_config[handler]["active"]
        # Every activated test handler should be in the active handlers
        for test_handler, config in handlers_config.items():
            if config["active"]:
                assert test_handler in active_handlers
            else:
                assert test_handler not in active_handlers
