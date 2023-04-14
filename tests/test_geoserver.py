# pylint: disable=protected-access
"""
These tests require a working Geoserver instance.

They are ignored by the `Make test` target and the CI, but are
still useful for a developer working on the Geoserver requests. They can be run with the `Make test-geoserver` target.
More integration tests should be in Jupyter Notebook format as is the case with Birdhouse-deploy / DACCS platform.
"""
import glob
import mock
import os
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

from cowbird.constants import COWBIRD_ROOT
from cowbird.handlers import HandlerFactory
from cowbird.handlers.impl.filesystem import DEFAULT_UID, DEFAULT_GID
from cowbird.handlers.impl.geoserver import Geoserver, GeoserverError, SHAPEFILE_MAIN_EXTENSION
from cowbird.handlers.impl.magpie import WFS_READ_PERMISSIONS, WMS_READ_PERMISSIONS, WFS_WRITE_PERMISSIONS
from cowbird.permissions_synchronizer import Permission
from tests import utils

CURR_DIR = Path(__file__).resolve().parent


def get_geoserver_settings():
    """
    Setup basic parameters for an unmodified local test run (using the example files) unless environment variables are
    set.
    """
    load_dotenv(CURR_DIR / "../docker/.env.example")
    config_path = os.path.join(COWBIRD_ROOT, "config/config.example.yml")
    app = utils.get_test_app(settings={"cowbird.config_path": config_path})
    with open(config_path, "r", encoding="utf-8") as f:
        settings_dictionary = yaml.safe_load(f)
    geoserver_settings = settings_dictionary["handlers"]["Geoserver"]
    geoserver_settings["url"] = os.getenv("COWBIRD_TEST_GEOSERVER_URL")
    if "${HOSTNAME}" in geoserver_settings["url"]:
        hostname = os.getenv("HOSTNAME", "localhost")
        geoserver_settings["url"] = geoserver_settings["url"].replace("${HOSTNAME}", hostname)
    if "${WORKSPACE_DIR}" in geoserver_settings["workspace_dir"]:
        # Make sure the user running this test has write access to this directory and that this path
        # is also the one used in the docker-compose environment file (docker/.env | docker/.env.example)
        value = os.getenv("WORKSPACE_DIR", "/tmp/user_workspace")
        geoserver_settings["workspace_dir"] = geoserver_settings["workspace_dir"].replace("${WORKSPACE_DIR}", value)
    if "${GEOSERVER_ADMIN}" in geoserver_settings["admin_user"]:
        value = os.getenv("GEOSERVER_ADMIN", "")
        geoserver_settings["admin_user"] = geoserver_settings["admin_user"].replace("${GEOSERVER_ADMIN}", value)
    if "${GEOSERVER_PASSWORD}" in geoserver_settings["admin_password"]:
        value = os.getenv("GEOSERVER_PASSWORD", "")
        geoserver_settings["admin_password"] = geoserver_settings["admin_password"].replace("${GEOSERVER_PASSWORD}",
                                                                                            value)
    geoserver_settings["ssl_verify"] = os.getenv("COWBIRD_SSL_VERIFY", False)
    return geoserver_settings


def copy_shapefile(basename, destination):
    full_filename = f"{COWBIRD_ROOT}/tests/resources/{basename}"
    Path(destination).mkdir(parents=True, exist_ok=False)
    for file in glob.glob(f"{full_filename}.*"):
        shutil.copy(file, destination)


@pytest.mark.online
@pytest.mark.geoserver
class TestGeoserverRequests:
    geoserver_settings = get_geoserver_settings()
    workspaces = {
        "creation": "test-workspace-creation",
        "creation-duplicate": "test-duplicate-workspace",
        "empty-remove": "test-empty-workspace-removal",
        "remove": "test-workspace-removal",
        "datastore-create": "test-datastore-creation",
        "datastore-config": "test-datastore-configuration",
        "datastore-duplicate": "test-duplicate-datastore",
        #"publish_remove": "test_publish_remove_shapefile"
        "publish_remove": "test_user"
    }
    # Be careful of typos or path choisec, as the paths contained in the following dictionary
    # will the removed during teardown.
    folders = {
        "publish_remove": geoserver_settings["workspace_dir"] + "/" + workspaces["publish_remove"]
    }

    @pytest.fixture
    def geoserver(self):
        # Bypasses HandlerFactory() to prevent side effects in other tests.
        geoserver = Geoserver(settings={}, name="Geoserver", **self.geoserver_settings)
        geoserver.ssl_verify = self.geoserver_settings["ssl_verify"]
        return geoserver

    def teardown_class(self):
        # Couldn't pass fixture to teardown function.
        teardown_gs = Geoserver(settings={}, name="Geoserver", **self.geoserver_settings)
        teardown_gs.ssl_verify = self.geoserver_settings["ssl_verify"]
        for _, workspace in self.workspaces.items():
            try:
                teardown_gs._remove_workspace_request(workspace_name=workspace)
            except GeoserverError:
                # Making sure all test workspaces are removed
                pass
        for _, folder in self.folders.items():
            try:
                if folder == "/":
                    raise PermissionError("Tests tried to remove the '/' path.")
                shutil.rmtree(folder)
            except FileNotFoundError:
                pass

    def test_workspace_creation(self, geoserver):
        response = geoserver._create_workspace_request(workspace_name=self.workspaces["creation"])
        assert response.status_code == 201

    def test_empty_workspace_removal(self, geoserver):
        geoserver._create_workspace_request(self.workspaces["empty-remove"])
        response = geoserver._remove_workspace_request(workspace_name=self.workspaces["empty-remove"])
        assert response.status_code == 200

    def test_duplicate_workspace(self, geoserver):
        response = geoserver._create_workspace_request(workspace_name=self.workspaces["creation-duplicate"])
        assert response.status_code == 201
        response = geoserver._create_workspace_request(workspace_name=self.workspaces["creation-duplicate"])
        assert response.status_code == 401

    def test_workspace_removal(self, geoserver):
        geoserver._create_workspace_request(workspace_name=self.workspaces["remove"])
        geoserver._create_datastore_request(workspace_name=self.workspaces["remove"],
                                            datastore_name="test-datastore")
        response = geoserver._remove_workspace_request(workspace_name=self.workspaces["remove"])
        assert response.status_code == 200

    def test_datastore_creation(self, geoserver):
        geoserver._create_workspace_request(workspace_name=self.workspaces["datastore-create"])
        response = geoserver._create_datastore_request(workspace_name=self.workspaces["datastore-create"],
                                                       datastore_name="test-datastore")
        assert response.status_code == 201

    def test_datastore_creation_missing_workspace(self, geoserver):
        with pytest.raises(GeoserverError) as error:
            geoserver._create_datastore_request(workspace_name="test-nonexistent-workspace",
                                                datastore_name="test-datastore")
        assert "Operation [_create_datastore_request] failed" in str(error.value)

    def test_datastore_configuration(self, geoserver):
        geoserver._create_workspace_request(workspace_name=self.workspaces["datastore-config"])
        geoserver._create_datastore_request(workspace_name=self.workspaces["datastore-config"],
                                            datastore_name="test-datastore")

        response = geoserver._configure_datastore_request(workspace_name=self.workspaces["datastore-config"],
                                                          datastore_name="test-datastore",
                                                          datastore_path=geoserver.workspace_dir)
        assert response.status_code == 200

    def test_duplicate_datastore(self, geoserver):
        geoserver._create_workspace_request(workspace_name=self.workspaces["datastore-duplicate"])
        response = geoserver._create_datastore_request(workspace_name=self.workspaces["datastore-duplicate"],
                                                       datastore_name="test-datastore")
        assert response.status_code == 201

        with pytest.raises(GeoserverError) as error:
            geoserver._create_datastore_request(workspace_name=self.workspaces["datastore-duplicate"],
                                                datastore_name="test-datastore")
        assert "Operation [_create_datastore_request] failed" in str(error.value)

    # Mock the chown function to avoid fail in case the tests are run as non-root
    @mock.patch("os.chown")
    def test_publish_and_remove_shapefile(self, mock_chown, geoserver):
        # Creating workspace and datastore needed to publish a shapefile
        workspace_name = self.workspaces["publish_remove"]
        datastore_name = "test-datastore-publish_remove"
        geoserver_workspace_path = f"/user_workspaces/{workspace_name}/shapefile_datastore"
        geoserver._create_workspace_request(workspace_name=workspace_name)
        geoserver._create_datastore_request(workspace_name=workspace_name,
                                            datastore_name=datastore_name)
        geoserver._configure_datastore_request(workspace_name=workspace_name,
                                               datastore_name=datastore_name,
                                               datastore_path=geoserver_workspace_path)

        # Preparations needed to make tests work without all the other handlers running
        shapefile_name = "Espace_Vert"
        workspace_path = self.folders["publish_remove"] + "/shapefile_datastore"
        shapefile_list = geoserver.get_shapefile_list(workspace_name, shapefile_name)
        # This next part can fail if the user running this test doesn't have write access to the directory
        copy_shapefile(basename=shapefile_name, destination=workspace_path)

        # Validate and publish shapefile
        geoserver.validate_shapefile(workspace_name=workspace_name, shapefile_name=shapefile_name)
        response = geoserver._publish_shapefile_request(workspace_name, datastore_name, shapefile_name)
        assert response.status_code == 201

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg") as cfg_file:
            cfg_file.write(yaml.safe_dump({
                "handlers": {
                    "Magpie": {
                        "active": True,
                        "url": os.getenv("COWBIRD_TEST_MAGPIE_URL"),
                        "admin_user": os.getenv("MAGPIE_ADMIN_USER"),
                        "admin_password": os.getenv("MAGPIE_ADMIN_PASSWORD")
                    }}}))
            cfg_file.flush()
            app = utils.get_test_app(settings={"cowbird.config_path": cfg_file.name})

            # Recreate new magpie handler instance with new config
            magpie = HandlerFactory().create_handler("Magpie")

            # Create geoserver service
            magpie.delete_service("geoserver")
            data = {
                "service_name": "geoserver",
                "service_type": "geoserver",
                "service_url": f"http://localhost:9000/geoserver",
            }
            magpie.create_service(data)

            user_name = workspace_name
            magpie.delete_user(user_name)
            magpie.create_user(user_name, "test@test.com", "qwertyqwerty", "users")

            for file in shapefile_list:
                os.chmod(file, 0o500)

            geoserver.on_created(os.path.join(workspace_path, shapefile_name + SHAPEFILE_MAIN_EXTENSION))

            geoserver_resources = magpie.get_resources_by_service("geoserver")
            workspace_res = list(geoserver_resources["resources"].values())[0]
            workspace_res_id = workspace_res["resource_id"]
            shapefile_res_id = list(workspace_res["children"])[0]

            # Check if the user has the right permissions on Magpie
            user_permissions = magpie.get_user_permissions_by_res_id(user_name, shapefile_res_id, effective=True)
            read_permissions = set(WFS_READ_PERMISSIONS + WMS_READ_PERMISSIONS)
            assert read_permissions == set([p["name"] for p in
                                            user_permissions["permissions"] if p["access"] == "allow"])
            expected_chown_shapefile_calls = [mock.call(file, DEFAULT_UID, DEFAULT_GID) for file in shapefile_list]
            utils.check_mock_has_calls_exactly(mock_chown, expected_chown_shapefile_calls)

            for file in shapefile_list:
                os.chmod(file, 0o000)

            # Update shapefile read permissions
            new_permission = Permission(
                service_name="geoserver",
                resource_id=shapefile_res_id,
                resource_full_name=f"/geoserver/{workspace_name}/{shapefile_name}",
                name="describefeaturetype",
                access="allow",
                scope="recursive",
                user=workspace_name
            )
            geoserver.permission_created(new_permission)
            utils.check_mock_has_calls_exactly(mock_chown, expected_chown_shapefile_calls)
            for file in shapefile_list:
                utils.check_file_permissions(file, 0o500)

            # Make sure workspace has only read permissions
            os.chmod(workspace_path, 0o500)
            magpie.create_permission_by_user_and_res_id(user_name, workspace_res_id, {
                        "permission": {
                            "name": "describefeaturetype",
                            "access": "allow",
                            "scope": "match"
                        }})
            # Update workspace with write permissions
            new_permission.name = "createstoredquery"
            new_permission.resource_id = workspace_res_id
            new_permission.resource_full_name = f"/geoserver/{workspace_name}"
            magpie.create_permission_by_user_and_res_id(user_name, workspace_res_id, {
                        "permission": {
                            "name": new_permission.name,
                            "access": new_permission.access,
                            "scope": new_permission.scope
                        }})
            geoserver.permission_created(new_permission)
            utils.check_mock_has_calls_exactly(mock_chown, [mock.call(workspace_path, DEFAULT_UID, DEFAULT_GID)] +
                                               expected_chown_shapefile_calls)
            utils.check_file_permissions(workspace_path, 0o700)
            for file in shapefile_list:
                utils.check_file_permissions(file, 0o700)

            # TODO: add test case sur service

            # # Delete file on storage, it should be redownloaded from Geoserver during a permission_created event.
            # TODO: expect error
            # os.remove(workspace_path + f"/{shapefile_name}.shp")

            # Remove shapefile
            response = geoserver._remove_shapefile_request(workspace_name, datastore_name, shapefile_name)
            assert response.status_code == 200

            # Resource should only removed when the file is deleted from the filesystem?
            # TODO: Check if resource was removed on Magpie

            magpie.delete_service("geoserver")
        utils.clear_handlers_instances()
