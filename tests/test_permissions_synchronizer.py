import contextlib
import os
import tempfile
import unittest

import mock
import pytest
import yaml

from cowbird.permissions_synchronizer import Permission, PermissionSynchronizer
from cowbird.services.service_factory import ServiceFactory
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
                "Magpie": {"active": True},
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
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("cowbird.services.impl.magpie.Magpie",
                                           side_effect=utils.MockMagpieService))
            stack.enter_context(mock.patch("cowbird.services.impl.geoserver.Geoserver",
                                           side_effect=utils.MockAnyService))
            stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                           side_effect=utils.MockAnyService))

            magpie = ServiceFactory().get_service("Magpie")

            resource_name = "resource1"
            for svc in self.test_services:
                for perm_name in self.sync_perm_name[svc]:
                    permission = Permission(
                        service_name=svc,
                        resource_id="0",
                        resource_full_name=self.res_root[svc] + resource_name,
                        name=perm_name,
                        access="string1",
                        scope="string2",
                        user="string3")
                    PermissionSynchronizer(magpie).create_permission(permission)
                    assert len(magpie.json()["outbound_perms"]) == len(self.sync_perm_name[self.mapped_service[svc]])
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
                    PermissionSynchronizer(magpie).delete_permission(permission)
                    assert len(magpie.json()["outbound_perms"]) == 0
