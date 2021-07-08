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
        data = {
            "services": {
                "Catalog": {"active": False},
                "Geoserver": {"active": True},
                "Magpie": {"active": True},
                "Nginx": {"active": True},
                "Thredds": {"active": True}
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

    def test_service_factory(self):
        # Test singleton
        inst1 = ServiceFactory().get_service("Magpie")
        inst2 = ServiceFactory().get_service("Magpie")
        assert inst1 is inst2
        assert len(ServiceFactory().services) == 1
        assert ServiceFactory().services["Magpie"] is inst1

        # Test services config
        services = ServiceFactory().get_active_services()
        assert services[0].name == "Geoserver"
        assert services[1].name == "Magpie"
        assert services[2].name == "Nginx"
        assert services[3].name == "Thredds"
