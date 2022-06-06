import os
import tempfile
import unittest

import pytest
import yaml

from cowbird.config import MULTI_TOKEN, ConfigErrorInvalidResourceKey, ConfigErrorInvalidServiceKey, \
    ConfigErrorInvalidTokens, ConfigError
from cowbird.services import ServiceFactory
from cowbird.services.impl.magpie import MAGPIE_ADMIN_PASSWORD_TAG, MAGPIE_ADMIN_USER_TAG
from tests import utils


def check_config(config_data, expected_exception_type=None):
    """
    Checks if the config loads without error, or if it triggers the expected exception in the case of an invalid config.
    """
    cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)
    with cfg_file as f:
        f.write(yaml.safe_dump(config_data))
    if expected_exception_type:
        utils.check_raises(lambda: utils.get_test_app(settings={"cowbird.config_path": f.name}),
                           expected_exception_type, msg="invalid config file should raise")
    else:
        utils.get_test_app(settings={"cowbird.config_path": f.name})
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
                "Thredds": {"active": True},
                "Geoserver": {"active": True}
            }
        }

    def test_not_unique_multitoken(self):
        """
        Tests if config respects the constraint of using maximum one `MULTI_TOKEN` in a single resource.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Valid_multitoken": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}
                        ]}},
                "permissions_mapping": []
            }
        }
        check_config(self.data)

        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Invalid_multitoken": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"},
                            {"name": MULTI_TOKEN, "type": "directory"}
                        ]}},
                "permissions_mapping": []
            }
        }
        check_config(self.data, ConfigErrorInvalidTokens)

    def test_not_unique_named_token(self):
        """
        Tests an invalid config where duplicate named tokens are used in a single resource.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Duplicate_tokens": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir_var}", "type": "directory"},
                            {"name": "{dir_var}", "type": "directory"}
                        ]}},
                "permissions_mapping": []
            }
        }
        check_config(self.data, ConfigErrorInvalidTokens)

    def test_webhooks_invalid_service(self):
        """
        Tests the cases where a service used in the `sync_permissions` section of the config is not defined and invalid.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "Invalid_Service": {
                        "Invalid": [
                            {"name": "catalog", "type": "service"},
                            {"name": "dir", "type": "directory"}]}},
                "permissions_mapping": []
            }
        }
        cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)
        with cfg_file as f:
            f.write(yaml.safe_dump(self.data))

        utils.get_test_app(settings={"cowbird.config_path": f.name})

        ServiceFactory().create_service("Magpie")
        # TODO: re-add mocking
        # TODO: check if creating Permissions_Synchronizer, triggers a ConfigError
        os.unlink(cfg_file.name)

    def test_unknown_res_key(self):
        """
        Tests an invalid config where an unknown resource key is found in the permissions_mapping.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "ValidResource": [
                            {"name": "catalog", "type": "service"}
                        ]}},
                "permissions_mapping": ["ValidResource : read <-> UnknownResource : read"]
            }
        }
        check_config(self.data, ConfigErrorInvalidResourceKey)

    def test_duplicate_resource_key(self):
        """
        Tests an invalid config where the same resource key is used for different resources.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "DuplicateResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": "dir", "type": "directory"}],
                        "OtherResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": "file", "type": "file"}]},
                    "geoserver": {
                        "DuplicateResource": [
                            {"name": "catalog", "type": "workspace"},
                            {"name": "dir", "type": "workspace"}]}
                },
                "permissions_mapping": ["DuplicateResource : read <-> OtherResource : read"]
            }
        }
        check_config(self.data, ConfigErrorInvalidResourceKey)

    def test_invalid_mapping_format(self):
        """
        Tests an invalid config where a permissions_mapping uses an invalid format.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "ValidResource": [
                            {"name": "catalog", "type": "service"}
                        ],
                        "ValidResource2": [
                            {"name": "catalog", "type": "service"}
                        ]}},
                "permissions_mapping": ["ValidResource : read <-> Invalid-format"]
            }
        }
        check_config(self.data, ConfigError)

    def test_multi_token_bidirectional(self):
        """
        Tests the usage of MULTI_TOKEN in a bidirectional mapping.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "TokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}],
                        "UntokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"},
                            {"name": "file", "type": "file"}
                        ]}},
                "permissions_mapping": ["TokenizedResource : read <-> UntokenizedResource : read"]
            }
        }
        check_config(self.data)

        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "TokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}],
                        "UntokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": "file", "type": "file"}
                        ]}},
                "permissions_mapping": ["TokenizedResource : read <-> UntokenizedResource : read"]
            }
        }
        check_config(self.data, ConfigErrorInvalidTokens)

    def test_unidirectional_multi_token(self):
        """
        Tests the usage of MULTI_TOKEN in a unidirectional mapping.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "TokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": MULTI_TOKEN, "type": "directory"}],
                        "UntokenizedResource": [
                            {"name": "catalog", "type": "service"},
                            {"name": "file", "type": "file"}
                        ]}},
                "permissions_mapping": ["TokenizedResource : read -> UntokenizedResource : read"]
            }
        }
        check_config(self.data)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            ["UntokenizedResource : read -> TokenizedResource : read"]
        check_config(self.data, ConfigErrorInvalidTokens)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            ["TokenizedResource : read <- UntokenizedResource : read"]
        check_config(self.data, ConfigErrorInvalidTokens)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            ["UntokenizedResource : read <- TokenizedResource : read"]
        check_config(self.data)

    def test_bidirectional_named_tokens(self):
        """
        Tests config with a bidirectional mapping that uses named tokens.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Resource1": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "{dir2_var}", "type": "directory"}],
                        "Resource2": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir2_var}", "type": "directory"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "dir2", "type": "directory"}
                        ]}},
                "permissions_mapping": ["Resource1 : read <-> Resource2 : read"]
            }
        }
        check_config(self.data)

        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Resource1": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "{dir2_var}", "type": "directory"}],
                        "Resource2": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "dir2", "type": "directory"}
                        ]}},
                "permissions_mapping": ["Resource1 : read <-> Resource2 : read"]
            }
        }
        check_config(self.data, ConfigErrorInvalidTokens)

    def test_unidirectional_named_tokens(self):
        """
        Tests config with a unidirectional mapping that uses named tokens.
        """
        self.data["sync_permissions"] = {
            "user_workspace": {
                "services": {
                    "thredds": {
                        "Resource1": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "{dir2_var}", "type": "directory"}],
                        "Resource2": [
                            {"name": "catalog", "type": "service"},
                            {"name": "{dir1_var}", "type": "directory"},
                            {"name": "dir2", "type": "directory"}
                        ]}},
                "permissions_mapping": ["Resource1 : read -> Resource2 : read"]
            }
        }
        check_config(self.data)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            ["Resource2 : read -> Resource1 : read"]
        check_config(self.data, ConfigErrorInvalidTokens)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            ["Resource1 : read <- Resource2 : read"]
        check_config(self.data, ConfigErrorInvalidTokens)

        self.data["sync_permissions"]["user_workspace"]["permissions_mapping"] = \
            ["Resource2 : read <- Resource1 : read"]
        check_config(self.data)
