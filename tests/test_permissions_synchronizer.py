import contextlib
import os
import tempfile
import unittest

import mock
import pytest
import yaml

from cowbird.config import MULTI_TOKEN, ConfigErrorInvalidResourceKey, ConfigErrorInvalidServiceKey, \
    ConfigErrorInvalidTokens, ConfigError
from cowbird.permissions_synchronizer import Permission, PermissionSynchronizer
from cowbird.services import ServiceFactory
from cowbird.services.impl.magpie import MAGPIE_ADMIN_PASSWORD_TAG, MAGPIE_ADMIN_USER_TAG
from tests import utils


@pytest.mark.permissions
class TestSyncPermissions(unittest.TestCase):
    """
    Test permissions synchronization.
    """

    @classmethod
    def setUpClass(cls):
        service1 = "Geoserver"
        service2 = "Thredds"
        cls.test_services = [service1, service2]
        cls.res_root = {service1: "/api/workspaces/private/",
                        service2: "/catalog/birdhouse/workspaces/private/"}
        cls.sync_perm_name = {service1: ["read"],
                              service2: ["read", "browse"]}
        mapping_point_1 = "mapping_point_1"
        cls.mapped_service = {service1: service2,
                              service2: service1}
        data = {
            "services": {
                "Magpie": {"active": True, "url": ""},
                service1: {"active": True},
                service2: {"active": True}
            },
            "sync_permissions": {
                mapping_point_1: {
                    "services": {
                        service1: cls.res_root[service1],
                        service2: cls.res_root[service2]
                    },
                    "permissions_mapping": [
                        {
                            service1: cls.sync_perm_name[service1],
                            service2: cls.sync_perm_name[service2]
                        }
                    ]
                }
            }

        }
        cls.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)
        with cls.cfg_file as f:
            f.write(yaml.safe_dump(data))
        cls.app = utils.get_test_app(settings={"cowbird.config_path": cls.cfg_file.name})

    @classmethod
    def tearDownClass(cls):
        utils.clear_services_instances()
        os.unlink(cls.cfg_file.name)

    def test_sync(self):
        """
        This test parses the sync config and checks that when a permission is created in the `PermissionSynchronizer`
        the proper permission is created for every synchronized service.
        The `PermissionSynchronizer` `create_permission` function will first find if the applied permission exists in
        the config. Then for every configured service it will obtain the equivalent permission for this service and
        apply it to the mocked Magpie service. The `outbound_perm` dict of the mocked Magpie service is then checked
        to validate that every permission that should have been created in Magpie exists.
        """
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.magpie.Magpie",
                                           side_effect=utils.MockMagpieService))
            stack.enter_context(mock.patch("cowbird.services.impl.geoserver.Geoserver",
                                           side_effect=utils.MockAnyService))
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))

            magpie = ServiceFactory().get_service("Magpie")

            resource_name = "resource1"
            # Loop over every service having a permission that must be synchronized to another one
            for svc in self.test_services:
                for perm_name in self.sync_perm_name[svc]:
                    # Create the permission for this service that would be provided by `Magpie` as a hook
                    permission = Permission(
                        service_name=svc,
                        resource_id="0",
                        resource_full_name=self.res_root[svc] + resource_name,
                        name=perm_name,
                        access="string1",
                        scope="string2",
                        user="string3")

                    # Apply this permission to the synchronizer (this is the function that is tested!)
                    PermissionSynchronizer(magpie).create_permission(permission)

                    # `magpie`, which is mocked, will store every permission request that should have been done to the
                    # Magpie service in the `outbound_perms` dict.
                    assert len(magpie.json()["outbound_perms"]) == len(self.sync_perm_name[self.mapped_service[svc]])

                    # Validate that the mocked `magpie` instance has received a permission request for every mapped
                    # permission
                    for idx, mapped_perm_name in enumerate(self.sync_perm_name[self.mapped_service[svc]]):
                        outbound_perm = magpie.json()["outbound_perms"][idx]
                        assert outbound_perm.service_name == self.mapped_service[svc]
                        assert outbound_perm.resource_id == utils.MockAnyService.ResourceId
                        assert outbound_perm.resource_full_name == \
                            self.res_root[self.mapped_service[svc]] + resource_name
                        assert outbound_perm.name == mapped_perm_name
                        assert outbound_perm.access == permission.access
                        assert outbound_perm.scope == permission.scope
                        assert outbound_perm.user == permission.user

                    # This is the second function being tested which should make remove permission requests to `magpie`
                    # for every mapped permission
                    PermissionSynchronizer(magpie).delete_permission(permission)

                    # Again the mocked `magpie` instance should remove every permission from its `outbound_perms` rather
                    # than making the remove permission request to the Magpie service.
                    assert len(magpie.json()["outbound_perms"]) == 0


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
