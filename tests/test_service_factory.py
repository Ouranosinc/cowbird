import unittest

import pytest

from cowbird.services.service_factory import ServiceFactory
from tests import utils


@pytest.mark.service_factory
class TestServiceFactory(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = utils.get_test_app(settings={"cowbird.config_path": utils.TEST_CFG_FILE})

    @classmethod
    def tearDownClass(cls):
        utils.clear_services_instances()

    def test_service_factory(self):
        # Test singleton
        inst1 = ServiceFactory().get_service("Magpie")
        inst2 = ServiceFactory().get_service("Magpie")
        assert inst1 is inst2
        assert len(ServiceFactory().services) == 1
        assert ServiceFactory().services["Magpie"] is inst1

        # Test services config
        services = ServiceFactory().get_active_services()
        assert services[0].name == "Magpie"
        assert services[1].name == "Geoserver"
        assert services[2].name == "Thredds"
        assert services[3].name == "Nginx"
