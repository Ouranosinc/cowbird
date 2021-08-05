import os
import tempfile
import unittest

import pytest
import yaml

from cowbird.services.service import SERVICE_URL_PARAM, SERVICE_WORKSPACE_DIR_PARAM, ServiceConfigurationException
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
        cls.priority = ["Thredds", "Magpie"]
        for idx, svc in enumerate(cls.priority):
            cls.test_data["services"][svc]["priority"] = idx
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

        # Prioritize services should appear in the proper order
        for idx, svc in enumerate(self.priority):
            assert active_services[idx] == svc

    def test_service_configuration(self):
        invalid_config = {"active": True, SERVICE_URL_PARAM: ""}
        valid_config = {"active": True, SERVICE_URL_PARAM: "https://service.domain", SERVICE_WORKSPACE_DIR_PARAM: "/"}

        # Should raise if the config does not include a required param
        with pytest.raises(ServiceConfigurationException):
            GoodService(ServiceFactory().settings, "GoodService", **invalid_config)

        # Should raise if the service does not define its required params
        with pytest.raises(NotImplementedError):
            BadService(ServiceFactory().settings, "BadService", **valid_config)

        # Should raise if a service defines an invalid param
        with pytest.raises(Exception):
            BadParamService("BadParamService", **valid_config)

        svc = GoodService(ServiceFactory().settings, "GoodService", **valid_config)
        assert getattr(svc, SERVICE_URL_PARAM) == valid_config[SERVICE_URL_PARAM]
        assert getattr(svc, SERVICE_WORKSPACE_DIR_PARAM) == valid_config[SERVICE_WORKSPACE_DIR_PARAM]


class BadService(utils.MockAnyServiceBase):
    #  This service is bad because Service implementation must define the required_params variable
    pass


class BadParamService(utils.MockAnyServiceBase):
    #  This service is bad because the required_params must only include param from the frozen set SERVICE_PARAMETERS
    required_params = [SERVICE_URL_PARAM, SERVICE_WORKSPACE_DIR_PARAM, "Invalid_param_name"]


class GoodService(utils.MockAnyServiceBase):
    # This service is good param wise and should be properly configured
    required_params = [SERVICE_URL_PARAM, SERVICE_WORKSPACE_DIR_PARAM]
