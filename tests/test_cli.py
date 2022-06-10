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
import yaml

from cowbird.cli import main as cowbird_cli
from cowbird.config import get_all_configs
from tests.utils import TEST_CFG_FILE, TEST_INI_FILE

KNOWN_HELPERS = [
    "services",
]


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
def test_cowbird_services_list_with_formats():
    override = {"COWBIRD_CONFIG_PATH": TEST_CFG_FILE}
    # with open(TEST_CFG_FILE, "r", encoding="utf-8") as f:
    #     cfg = yaml.safe_load(f)
    svcs_config = get_all_configs(TEST_CFG_FILE, "services")[0]
    # TODO: Voir comment setter les variables d<environnement (utiliser python-dotenv + .env.example?)
    #   woud probably work, but maybe check if cowbird works in general, or if those variables are also never set
    #   if cowbird fails too, maybe do it elsewhere?
    with mock.patch.dict("os.environ", override):
        out_lines = run_and_get_output(f"cowbird services list -f yaml -c '{TEST_INI_FILE}'")
        assert out_lines[0] == "services:"
        out_lines = run_and_get_output(f"cowbird services list -f json -c '{TEST_INI_FILE}'", trim=False)
        assert out_lines[0] == "{"
        assert '"services": [' in out_lines[1]  # pylint: disable=C4001
        out_lines = run_and_get_output(f"cowbird services list -f table -c '{TEST_INI_FILE}'")
        assert "+---" in out_lines[0]
        assert "| services" in out_lines[1]
        assert "+===" in out_lines[2]

        # Test services config
        active_services = [line.strip("|").strip(" ") for line in out_lines[3:-1]]
        # Every active service should be in test data
        for service in active_services:
            assert service in svcs_config
            assert svcs_config[service]["active"]
        # Every activated test service should be in the active services
        for test_service, config in svcs_config.items():
            if config["active"]:
                assert test_service in active_services
            else:
                assert test_service not in active_services
