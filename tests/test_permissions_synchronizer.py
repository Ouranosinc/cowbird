import contextlib
import tempfile
import unittest

import mock
import pytest
import yaml

from cowbird.permissions_synchronizer import Permission, PermissionSynchronizer
from cowbird.services.service_factory import ServiceFactory
from cowbird.utils import SingletonMeta
from tests import utils


@pytest.mark.permissions
class TestSyncPermissions(unittest.TestCase):
    """
    Test permissions synchronization.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = utils.get_test_app()

    @classmethod
    def tearDownClass(cls):
        # Remove the service instances initialized with the special sync cfg for next tests
        SingletonMeta._instances.clear()  # pylint: disable=W0212
        super(TestSyncPermissions, cls).tearDownClass()

    def test_sync(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg") as tmp:
            service1 = "Geoserver"
            service2 = "Thredds"
            test_services = [service1, service2]
            res_root = {service1: "/api/workspaces/private/",
                        service2: "/catalog/birdhouse/workspaces/private/"}
            sync_perm_name = {service1: ["read"],
                              service2: ["read", "browse"]}
            mapping_point_1 = "mapping_point_1"
            mapped_service = {service1: service2,
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
                            service1: res_root[service1],
                            service2: res_root[service2]
                        },
                        "permissions_mapping": [
                            {
                                service1: sync_perm_name[service1],
                                service2: sync_perm_name[service2]
                            }
                        ]
                    }
                }
            }
            tmp.write(yaml.safe_dump(data))
            tmp.seek(0)  # back to start since file still open (auto-delete if closed)
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch("cowbird.services.impl.magpie.Magpie",
                                               side_effect=utils.MockMagpieService))
                stack.enter_context(mock.patch("cowbird.services.impl.geoserver.Geoserver",
                                               side_effect=utils.MockAnyService))
                stack.enter_context(mock.patch("cowbird.services.impl.thredds.Thredds",
                                               side_effect=utils.MockAnyService))
                utils.get_test_app(settings={"cowbird.config_path": tmp.name})

                resource_name = "resource1"
                magpie = ServiceFactory().get_service("Magpie")

                for svc in test_services:
                    for perm_name in sync_perm_name[svc]:
                        permission = Permission(
                            service_name=svc,
                            resource_id=0,
                            resource_full_name=res_root[svc] + resource_name,
                            name=perm_name,
                            access="string1",
                            scope="string2",
                            user="string3")
                        PermissionSynchronizer(magpie).create_permission(permission)
                        assert len(magpie.json()["outbound_perms"]) == len(sync_perm_name[mapped_service[svc]])
                        for idx, mapped_perm_name in enumerate(sync_perm_name[mapped_service[svc]]):
                            outbound_perm = magpie.json()["outbound_perms"][idx]
                            assert outbound_perm.service_name == mapped_service[svc]
                            assert outbound_perm.resource_id == utils.MockAnyService.ResourceId
                            assert outbound_perm.resource_full_name == res_root[mapped_service[svc]] + resource_name
                            assert outbound_perm.name == mapped_perm_name
                            assert outbound_perm.access == permission.access
                            assert outbound_perm.scope == permission.scope
                            assert outbound_perm.user == permission.user
                        PermissionSynchronizer(magpie).delete_permission(permission)
                        assert len(magpie.json()["outbound_perms"]) == 0
