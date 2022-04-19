import os
import tempfile
import unittest

import pytest
import yaml

from cowbird.config import MULTI_TOKEN, SINGLE_TOKEN, ConfigErrorInvalidResourceKey, ConfigErrorInvalidTokens
from cowbird.services.impl.magpie import MAGPIE_ADMIN_PASSWORD_TAG, MAGPIE_ADMIN_USER_TAG
from tests import utils


def check_config_raises(config_data, exception_type):
    cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)
    with cfg_file as f:
        f.write(yaml.safe_dump(config_data))
    utils.check_raises(lambda: utils.get_test_app(settings={"cowbird.config_path": f.name}),
                       exception_type, msg="invalid config file should raise")
    os.unlink(cfg_file.name)


@pytest.mark.permissions
class TestSyncPermissionsConfig(unittest.TestCase):
    """
    Test config for permissions synchronization
    """
    def setUp(self):
        self.data = {
            "services": {
                "Magpie": {"active": True, "url": "",
                           MAGPIE_ADMIN_USER_TAG: "admin", MAGPIE_ADMIN_PASSWORD_TAG: "qwertyqwerty"},
                "Thredds": {"active": True}
            }
        }

    def test_name_after_token(self):
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "Thredds": {
                        "Invalid_name_after_token": [
                            {"name": "catalog", "type": "service"},
                            {"name": SINGLE_TOKEN, "type": "directory"},
                            {"name": "invalid_name", "type": "file"}
                        ]}},
                "permissions_mapping": []
            }
        }
        check_config_raises(self.data, ConfigErrorInvalidTokens)

    def test_not_unique_multitoken(self):
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "Thredds": {
                        "Invalid_multitoken": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"},
                            {"name": MULTI_TOKEN, "type": "directory"}
                        ]}},
                "permissions_mapping": []
            }
        }
        check_config_raises(self.data, ConfigErrorInvalidTokens)

    def test_unknown_res_key(self):
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "Thredds": {
                        "ValidResource": [
                            {"name": "catalog", "type": "service"}
                        ]}},
                "permissions_mapping": [
                    {"ValidResource": ["read"], "UnknownResource": ["read"]}
                ]
            }
        }
        check_config_raises(self.data, ConfigErrorInvalidResourceKey)

    def test_tokenized_res_with_untokenized_res(self):
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "Thredds": {
                        "TokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}],
                        "UntokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": "file", "type": "file"}
                        ]}},
                "permissions_mapping": [
                    {"TokenizedResource": ["read"], "UntokenizedResource": ["read"]}
                ]
            }
        }
        check_config_raises(self.data, ConfigErrorInvalidTokens)
