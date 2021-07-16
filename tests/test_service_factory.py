import os
import tempfile
import unittest

import pytest
import yaml

from cowbird.services.service_factory import ServiceFactory
from tests import utils


@pytest.mark.service_factory
class TestServiceFactory(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """
        Setup a config where 1 service is set inactive.
        """
        cls.test_data = {
            "services": {
                "Catalog": {"active": False},
                "Geoserver": {"active": True, "url": "", "workspace_dir": ""},
                "Magpie": {"active": True, "url": ""},
                "Nginx": {"active": True, "url": ""},
                "Thredds": {"active": True, "url": ""}
            }
        }
        cls.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)
        with cls.cfg_file as f:
            f.write(yaml.safe_dump(cls.test_data))
        cls.app = utils.get_test_app(settings={"cowbird.config_path": cls.cfg_file.name})

    @classmethod
    def tearDownClass(cls):
        utils.clear_services_instances()
        os.unlink(cls.cfg_file.name)

    def test_service_factory(self):
        # Test singleton
        inst1 = ServiceFactory().get_service("Magpie")
        inst2 = ServiceFactory().get_service("Magpie")
        assert inst1 is inst2
        assert len(ServiceFactory().services) == 1
        assert ServiceFactory().services["Magpie"] is inst1

        # Test services config
        active_services = [service.name for service in ServiceFactory().get_active_services()]
        # Every active service should be in test data
        for service in active_services:
            assert service in TestServiceFactory.test_data["services"]
            assert TestServiceFactory.test_data["services"][service]["active"]
        # Every activated test service should be in the active services
        for test_service, config in TestServiceFactory.test_data["services"].items():
            if config["active"]:
                assert test_service in active_services
            else:
                assert test_service not in active_services

    def test_service_configuration(self):
        pass
        # TODO: Required parameters validation
