import contextlib
import os
import tempfile
import unittest
from pathlib import Path

import mock
import pytest
import yaml
from dotenv import load_dotenv

from cowbird.handlers import HandlerFactory
from tests import utils

CURR_DIR = Path(__file__).resolve().parent


@pytest.mark.magpie
class TestMagpie(unittest.TestCase):
    """
    Tests different methods found in the Magpie handler.
    These tests require a running instance of Magpie.
    """

    @classmethod
    def setUpClass(cls):

        load_dotenv(CURR_DIR / "../docker/.env.example")

        cls.grp = "administrators"
        cls.usr = os.getenv("MAGPIE_ADMIN_USER")
        cls.pwd = os.getenv("MAGPIE_ADMIN_PASSWORD")
        cls.url = os.getenv("COWBIRD_TEST_MAGPIE_URL")

        # Reset handlers instances in case any are left from other test cases
        utils.clear_handlers_instances()

    def setUp(self):
        self.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)  # pylint: disable=R1732
        self.data = {
            "handlers": {
                "Magpie": {
                    "active": True,
                    "url": self.url,
                    "admin_user": self.usr,
                    "admin_password": self.pwd
                },
                "Thredds": {"active": True}
            }
        }
        with self.cfg_file as f:
            f.write(yaml.safe_dump(self.data))
        app = utils.get_test_app(settings={"cowbird.config_path": self.cfg_file.name})
        # Create new magpie handler instance with new config
        self.magpie = HandlerFactory().create_handler("Magpie")
        # Reset all magpie services for testing
        self.magpie.delete_all_services()

    def tearDown(self):
        utils.clear_handlers_instances()
        os.unlink(self.cfg_file.name)

    def test_get_or_create_layer_resource_id(self):
        """
        Tests the method used with geoserver to get a layer resource id.
        """

        workspace_name = "test_workspace"
        layer_name = "test_layer"

        # Should fail if no service exists in Magpie.
        with pytest.raises(ValueError):
            self.magpie.get_or_create_layer_resource_id(workspace_name, layer_name)

        data = {
            "service_name": "geoserver1",
            "service_type": "geoserver",
            "service_sync_type": "geoserver",
            "service_url": f"http://localhost:9000/geoserver",
            "configuration": {}
        }
        svc1_id = self.magpie.create_service(data)
        data["service_name"] = "geoserver2"
        svc2_id = self.magpie.create_service(data)

        # If workspace and layer don't yet exist, it should create both of them in the first service found.
        layer1_id = self.magpie.get_or_create_layer_resource_id(workspace_name, layer_name)
        created_id_parent_tree = self.magpie.get_parents_resource_tree(layer1_id)
        assert created_id_parent_tree[0]["resource_id"] == svc1_id

        # If the layer already exists, it should simply return the id found.
        existing_id = self.magpie.get_or_create_layer_resource_id(workspace_name, layer_name)
        assert existing_id == layer1_id

        # If another layer with the same name exists in another workspace, it should return the first id found.
        workspace2_id = self.magpie.create_resource(workspace_name, "workspace", svc2_id)
        layer2_id = self.magpie.create_resource(layer_name, "layer", workspace2_id)
        existing_id = self.magpie.get_or_create_layer_resource_id(workspace_name, layer_name)
        assert existing_id == layer1_id

        # If the layer does not exist yet, but the workspace exists, it creates the layer in the last workspace found.
        self.magpie.delete_resource(layer1_id)
        self.magpie.delete_resource(layer2_id)
        new_layer_id = self.magpie.get_or_create_layer_resource_id(workspace_name, layer_name)
        new_layer_parent_tree = self.magpie.get_parents_resource_tree(new_layer_id)
        assert new_layer_parent_tree[1]["resource_id"] == workspace2_id
