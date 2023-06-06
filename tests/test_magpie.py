# pylint: disable=protected-access
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml
from dotenv import load_dotenv
from magpie.models import Layer, Workspace
from magpie.services import ServiceGeoserver

from cowbird.handlers import HandlerFactory
from cowbird.handlers.impl.magpie import Magpie
from tests import utils

if TYPE_CHECKING:
    from typing import Dict

CURR_DIR = Path(__file__).resolve().parent


def create_user(magpie, user_name, email, password, group_name):
    # type: (Magpie, str, str, str, str) -> None
    resp = magpie._send_request(method="POST", url=f"{magpie.url}/users",
                                json={
                                    "user_name": user_name,
                                    "email": email,
                                    "password": password,
                                    "group_name": group_name
                                })
    assert resp.status_code == 201


def delete_user(magpie, user_name):
    # type: (Magpie, str) -> None
    resp = magpie._send_request(method="DELETE", url=f"{magpie.url}/users/{user_name}")
    assert resp.status_code in [200, 404]


def create_service(magpie, service_data):
    # type: (Magpie, Dict[str, str]) -> int
    resp = magpie._send_request(method="POST", url=f"{magpie.url}/services", json=service_data)
    assert resp.status_code == 201
    return resp.json()["service"]["resource_id"]


def delete_service(magpie, service_name):
    # type: (Magpie, str) -> None
    resp = magpie._send_request(method="DELETE", url=f"{magpie.url}/services/{service_name}")
    assert resp.status_code in [200, 404]


def delete_all_services(magpie):
    # type: (Magpie) -> None
    resp = magpie._send_request(method="GET", url=f"{magpie.url}/services")
    assert resp.status_code == 200
    for services_by_svc_type in resp.json()["services"].values():
        for svc in services_by_svc_type.values():
            delete_service(magpie, svc["service_name"])


@pytest.mark.magpie
class TestMagpie:
    """
    Tests different methods found in the Magpie handler.

    These tests require a running instance of Magpie.
    """

    # pylint: disable=attribute-defined-outside-init
    def setup_class(self):

        load_dotenv(CURR_DIR / "../docker/.env.example")

        self.grp = "administrators"
        self.usr = os.getenv("MAGPIE_ADMIN_USER")
        self.pwd = os.getenv("MAGPIE_ADMIN_PASSWORD")
        self.url = os.getenv("COWBIRD_TEST_MAGPIE_URL")

        # Reset handlers instances in case any are left from other test cases
        utils.clear_handlers_instances()

    # pylint: disable=attribute-defined-outside-init
    @pytest.fixture(autouse=True)
    def setup(self, tmpdir):
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
        self.cfg_filepath = tmpdir.strpath + "/test.cfg"
        with open(self.cfg_filepath, "w", encoding="utf-8") as f:
            f.write(yaml.safe_dump(self.data))

        # Set environment variables with config
        utils.get_test_app(settings={"cowbird.config_path": self.cfg_filepath})
        # Create new magpie handler instance with new config
        self.magpie = HandlerFactory().create_handler("Magpie")
        # Reset all magpie services for testing
        delete_all_services(self.magpie)
        yield
        utils.clear_handlers_instances()

    def test_get_or_create_layer_resource_id(self):
        """
        Tests the method used with geoserver to get a layer resource id.
        """

        workspace_name = "test_workspace"
        layer_name = "test_layer"

        # Should fail if no service exists in Magpie.
        with pytest.raises(ValueError):
            self.magpie.get_geoserver_layer_res_id(workspace_name, layer_name, create_if_missing=True)

        data = {
            "service_name": "geoserver1",
            "service_type": ServiceGeoserver.service_type,
            "service_sync_type": ServiceGeoserver.service_type,
            "service_url": "http://localhost:9000/geoserver",
            "configuration": {}
        }
        svc1_id = create_service(self.magpie, data)
        data["service_name"] = "geoserver2"
        svc2_id = create_service(self.magpie, data)

        # If workspace and layer don't yet exist, it should create both of them in the first service found.
        layer1_id = self.magpie.get_geoserver_layer_res_id(workspace_name, layer_name, create_if_missing=True)
        created_id_parent_tree = self.magpie.get_parents_resource_tree(layer1_id)
        assert created_id_parent_tree[0]["resource_id"] == svc1_id

        # If the layer already exists, it should simply return the id found.
        existing_id = self.magpie.get_geoserver_layer_res_id(workspace_name, layer_name, create_if_missing=True)
        assert existing_id == layer1_id

        # If another layer with the same name exists in another workspace, it should return the first id found.
        workspace2_id = self.magpie.create_resource(workspace_name, Workspace.resource_type_name, svc2_id)
        layer2_id = self.magpie.create_resource(layer_name, Layer.resource_type_name, workspace2_id)
        existing_id = self.magpie.get_geoserver_layer_res_id(workspace_name, layer_name, create_if_missing=True)
        assert existing_id == layer1_id

        # If the layer does not exist yet, but the workspace exists, it creates the layer in the last workspace found.
        self.magpie.delete_resource(layer1_id)
        self.magpie.delete_resource(layer2_id)
        new_layer_id = self.magpie.get_geoserver_layer_res_id(workspace_name, layer_name, create_if_missing=True)
        new_layer_parent_tree = self.magpie.get_parents_resource_tree(new_layer_id)
        assert new_layer_parent_tree[1]["resource_id"] == workspace2_id
