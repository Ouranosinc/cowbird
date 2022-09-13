import os
import tempfile
import unittest

import pytest
import yaml

from cowbird.handlers import get_handlers
from cowbird.handlers.handler import HANDLER_URL_PARAM, HANDLER_WORKSPACE_DIR_PARAM, HandlerConfigurationException
from cowbird.handlers.handler_factory import HandlerFactory
from tests import utils


@pytest.mark.handler_factory
class TestHandlerFactory(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """
        Setup a config where 1 handler is set inactive.
        """
        cls.test_data = {
            "handlers": {
                "Catalog": {"active": False},
                "Geoserver": {"active": True, "url": "", "workspace_dir": "", "admin_user": "", "admin_password": ""},
                "Magpie": {"active": True, "url": "", "admin_user": "admin", "admin_password": "qwertyqwerty"},
                "Nginx": {"active": True, "url": ""},
                "Thredds": {"active": True, "url": ""}
            }
        }
        cls.priority = ["Thredds", "Magpie"]
        for idx, handler in enumerate(cls.priority):
            cls.test_data["handlers"][handler]["priority"] = idx
        cls.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)  # pylint: disable=R1732
        with cls.cfg_file as f:
            f.write(yaml.safe_dump(cls.test_data))
        cls.app = utils.get_test_app(settings={"cowbird.config_path": cls.cfg_file.name})

        utils.clear_handlers_instances()

    @classmethod
    def tearDownClass(cls):
        utils.clear_handlers_instances()
        os.unlink(cls.cfg_file.name)

    def test_handler_factory(self):
        # Test singleton
        inst1 = HandlerFactory().get_handler("Magpie")
        inst2 = HandlerFactory().get_handler("Magpie")
        assert inst1 is inst2
        assert len(HandlerFactory().handlers) == 1
        assert HandlerFactory().handlers["Magpie"] is inst1

        # Test handlers config
        active_handlers = [handler.name for handler in get_handlers()]
        # Every active handler should be in test data
        for handler in active_handlers:
            assert handler in TestHandlerFactory.test_data["handlers"]
            assert TestHandlerFactory.test_data["handlers"][handler]["active"]

        # Every activated test handler should be in the active handlers
        for test_handler, config in TestHandlerFactory.test_data["handlers"].items():
            if config["active"]:
                assert test_handler in active_handlers
            else:
                assert test_handler not in active_handlers

        # Prioritize handlers should appear in the proper order
        for idx, handler in enumerate(self.priority):
            assert active_handlers[idx] == handler

    def test_handler_configuration(self):
        invalid_config = {"active": True, HANDLER_URL_PARAM: ""}
        valid_config = {"active": True, HANDLER_URL_PARAM: "https://handler.domain", HANDLER_WORKSPACE_DIR_PARAM: "/"}

        # Should raise if the config does not include a required param
        with pytest.raises(HandlerConfigurationException):
            GoodHandler(HandlerFactory().settings, "GoodHandler", **invalid_config)

        # Should raise if the handler does not define its required params
        with pytest.raises(NotImplementedError):
            BadHandler(HandlerFactory().settings, "BadHandler", **valid_config)

        # Should raise if a handler defines an invalid param
        with pytest.raises(Exception):
            BadParamHandler("BadParamHandler", **valid_config)

        handler = GoodHandler(HandlerFactory().settings, "GoodHandler", **valid_config)
        assert getattr(handler, HANDLER_URL_PARAM) == valid_config[HANDLER_URL_PARAM]
        assert getattr(handler, HANDLER_WORKSPACE_DIR_PARAM) == valid_config[HANDLER_WORKSPACE_DIR_PARAM]


class BadHandler(utils.MockAnyHandlerBase):
    #  This handler is bad because Handler implementation must define the required_params variable
    pass


class BadParamHandler(utils.MockAnyHandlerBase):
    #  This handler is bad because the required_params must only include param from the frozen set HANDLER_PARAMETERS
    required_params = [HANDLER_URL_PARAM, HANDLER_WORKSPACE_DIR_PARAM, "Invalid_param_name"]


class GoodHandler(utils.MockAnyHandlerBase):
    # This handler is good param wise and should be properly configured
    required_params = [HANDLER_URL_PARAM, HANDLER_WORKSPACE_DIR_PARAM]
