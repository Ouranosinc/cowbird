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
import unittest
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

from cowbird.constants import COWBIRD_ROOT
from cowbird.handlers import HandlerFactory
from cowbird.handlers.impl.filesystem import DEFAULT_UID, DEFAULT_GID
from cowbird.handlers.impl.geoserver import Geoserver, GeoserverError, SHAPEFILE_MAIN_EXTENSION
from cowbird.handlers.impl.magpie import LAYER_READ_PERMISSIONS, LAYER_WRITE_PERMISSIONS
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


def prepare_geoserver_test_workspace(test_instance, geoserver_handler, workspace_key):
    # Creating workspace and datastore needed to publish a shapefile
    workspace_name = test_instance.workspaces[workspace_key]
    datastore_name = f"test-datastore-{workspace_key}"
    geoserver_workspace_path = f"/user_workspaces/{workspace_name}/shapefile_datastore"
    geoserver_handler._create_workspace_request(workspace_name=workspace_name)
    geoserver_handler._create_datastore_request(workspace_name=workspace_name,
                                                datastore_name=datastore_name)
    geoserver_handler._configure_datastore_request(workspace_name=workspace_name,
                                                   datastore_name=datastore_name,
                                                   datastore_path=geoserver_workspace_path)

    # Preparations needed to make tests work without all the other handlers running
    datastore_path = get_datastore_path(test_instance.workspace_folders[workspace_key])
    # This next part can fail if the user running this test doesn't have write access to the directory
    copy_shapefile(basename=test_instance.test_shapefile_name, destination=datastore_path)

    return workspace_name, datastore_name


def copy_shapefile(basename, destination):
    full_filename = f"{COWBIRD_ROOT}/tests/resources/{basename}"
    Path(destination).mkdir(parents=True, exist_ok=False)
    for file in glob.glob(f"{full_filename}.*"):
        shutil.copy(file, destination)


def get_datastore_path(workspace_path):
    return workspace_path + "/shapefile_datastore"


class TestGeoserver():
    geoserver_settings = get_geoserver_settings()
    workspaces = {}
    workspace_folders = {}

    test_shapefile_name = "Espace_Vert"

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
        for _, folder in self.workspace_folders.items():
            try:
                # Make sure access permissions are enabled before deleting files
                os.chmod(folder, 0o777)
                for root, dirs, files in os.walk(folder):
                    for d in dirs:
                        os.chmod(os.path.join(root, d), 0o777)
                    for f in files:
                        os.chmod(os.path.join(root, f), 0o777)
                if folder == "/":
                    raise PermissionError("Tests tried to remove the '/' path.")
                shutil.rmtree(folder)
            except FileNotFoundError:
                pass

    @staticmethod
    def get_geoserver():
        geoserver = Geoserver(settings={}, name="Geoserver", **TestGeoserver.geoserver_settings)
        geoserver.ssl_verify = TestGeoserver.geoserver_settings["ssl_verify"]
        return geoserver


@pytest.mark.online
@pytest.mark.geoserver
class TestGeoserverRequests(TestGeoserver):

    workspaces = {
        "creation": "test-workspace-creation",
        "creation-duplicate": "test-duplicate-workspace",
        "empty-remove": "test-empty-workspace-removal",
        "remove": "test-workspace-removal",
        "datastore-create": "test-datastore-creation",
        "datastore-config": "test-datastore-configuration",
        "datastore-duplicate": "test-duplicate-datastore",
        "publish_remove": "test_publish_remove_shapefile"
    }
    # Be careful of typos or path choisec, as the paths contained in the following dictionary
    # will the removed during teardown.
    workspace_folders = {
        "publish_remove": f"{TestGeoserver.geoserver_settings['workspace_dir']}/{workspaces['publish_remove']}"
    }

    def teardown_class(self):
        TestGeoserver.teardown_class(self)

    @pytest.fixture
    def geoserver(self):
        # Bypasses HandlerFactory() to prevent side effects in other tests.
        return TestGeoserver.get_geoserver()

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

    def test_publish_and_remove_shapefile(self, geoserver):
        workspace_name, datastore_name = prepare_geoserver_test_workspace(self, geoserver, "publish_remove")

        # Validate and publish shapefile
        geoserver.validate_shapefile(workspace_name=workspace_name, shapefile_name=self.test_shapefile_name)
        response = geoserver._publish_shapefile_request(workspace_name, datastore_name, self.test_shapefile_name)
        assert response.status_code == 201

        # Remove shapefile
        response = geoserver._remove_shapefile_request(workspace_name, datastore_name, self.test_shapefile_name)
        assert response.status_code == 200


@pytest.mark.online
@pytest.mark.geoserver
@pytest.mark.magpie
class TestGeoserverPermissions(TestGeoserver):
    magpie_test_user = "test_user"
    workspaces = {
        magpie_test_user: magpie_test_user
    }
    workspace_folders = {
        magpie_test_user: f"{TestGeoserver.geoserver_settings['workspace_dir']}/{magpie_test_user}"
    }

    def setup_class(cls):
        # Reset handlers instances in case any are left from other test cases
        utils.clear_handlers_instances()

        cls.cfg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)  # pylint: disable=R1732

        with cls.cfg_file as f:
            f.write(yaml.safe_dump({
                "handlers": {
                    "Magpie": {
                        "active": True,
                        "url": os.getenv("COWBIRD_TEST_MAGPIE_URL"),
                        "admin_user": os.getenv("MAGPIE_ADMIN_USER"),
                        "admin_password": os.getenv("MAGPIE_ADMIN_PASSWORD")
                    }}}))

        app = utils.get_test_app(settings={"cowbird.config_path": cls.cfg_file.name})

        # Recreate new magpie handler instance with new config
        cls.magpie = HandlerFactory().create_handler("Magpie")

        # Mock the chown function to avoid fail in case the tests are run as non-root
        cls.patcher = mock.patch("os.chown")
        cls.mock_chown = cls.patcher.start()

    def teardown_class(cls):
        os.unlink(cls.cfg_file.name)

        cls.magpie.delete_user(cls.magpie_test_user)
        cls.magpie.delete_service("geoserver")
        utils.clear_handlers_instances()

        cls.patcher.stop()

        TestGeoserver.teardown_class(cls)

    @pytest.fixture(autouse=True)
    def setup(self):
        # Reset test user
        self.magpie.delete_user(self.magpie_test_user)
        self.magpie.create_user(self.magpie_test_user, "test@test.com", "qwertyqwerty", "users")

        # Reset geoserver service
        self.magpie.delete_service("geoserver")
        data = {
            "service_name": "geoserver",
            "service_type": "geoserver",
            "service_url": f"http://localhost:9000/geoserver",
        }
        self.test_service_id = self.magpie.create_service(data)

        self.geoserver = TestGeoserver.get_geoserver()

        # Setup workspace files
        self.workspace_name, self.datastore_name = prepare_geoserver_test_workspace(self, self.geoserver,
                                                                                  self.magpie_test_user)
        self.datastore_path = get_datastore_path(self.workspace_folders[self.magpie_test_user])
        self.shapefile_list = self.geoserver.get_shapefile_list(self.workspace_name, self.test_shapefile_name)
        os.chmod(self.datastore_path, 0o700)
        for file in self.shapefile_list:
            os.chmod(file, 0o000)

        # Setup service/resources
        self.layer_id = self.magpie.get_geoserver_resource_id(self.workspace_name, self.test_shapefile_name)
        parents_tree = self.magpie.get_parents_resource_tree(self.layer_id)

        self.workspace_res_id = parents_tree[-1]["parent_id"]

        self.expected_chown_shapefile_calls = \
            [mock.call(file, DEFAULT_UID, DEFAULT_GID) for file in self.shapefile_list]

    def check_magpie_permissions(self, layer_id, expected_perms, expected_chown_calls):
        user_permissions = self.magpie.get_user_permissions_by_res_id(self.magpie_test_user, layer_id, effective=True)
        assert expected_perms == set([p["name"] for p in user_permissions["permissions"] if p["access"] == "allow"])
        utils.check_mock_has_calls_exactly(self.mock_chown, expected_chown_calls)

    def test_shapefile_on_created(self):
        # For this test, remove service and check if the Magpie service and resources are recreated
        self.magpie.delete_service(self.test_service_id)

        for file in self.shapefile_list:
            os.chmod(file, 0o500)
        self.geoserver.on_created(os.path.join(self.datastore_path, self.test_shapefile_name + SHAPEFILE_MAIN_EXTENSION))

        geoserver_resources = self.magpie.get_resources_by_service("geoserver")
        workspace_res = list(geoserver_resources["resources"].values())[0]
        shapefile_res_id = list(workspace_res["children"])[0]

        # Check if the user has the right permissions on Magpie
        self.check_magpie_permissions(shapefile_res_id, set(LAYER_READ_PERMISSIONS), self.expected_chown_shapefile_calls)

    def test_shapefile_on_modified(self):
        # Test modifying a file's permissions
        os.chmod(self.shapefile_list[0], 0o700)
        self.geoserver.on_modified(os.path.join(self.datastore_path, self.test_shapefile_name + SHAPEFILE_MAIN_EXTENSION))

        self.check_magpie_permissions(self.layer_id, set(LAYER_READ_PERMISSIONS + LAYER_WRITE_PERMISSIONS),
                                      self.expected_chown_shapefile_calls)

    def test_shapefile_on_deleted(self):
        self.geoserver.on_deleted(self.datastore_path + f"/{self.test_shapefile_name}.shp")
        for file in self.shapefile_list:
            assert not os.path.exists(file)

        # Check that magpie layer resource was removed
        with pytest.raises(RuntimeError):
            self.magpie.get_user_permissions_by_res_id(self.magpie_test_user, self.layer_id)

# TODO: implement and add test cases for workspace changes on file system
    @pytest.mark.skip()
    def test_workspace_on_created(self):
        pass

    @pytest.mark.skip()
    def test_workspace_on_modified(self):
        pass

    @pytest.mark.skip()
    def test_workspace_on_deleted(self):
        pass

    def test_magpie_layer_permission_created(self):
        # Update shapefile read permissions
        layer_read_permission = Permission(
            service_name="geoserver",
            resource_id=str(self.layer_id),
            resource_full_name=f"/geoserver/{self.workspace_name}/{self.test_shapefile_name}",
            name="describefeaturetype",
            access="allow",
            scope="match",
            user=self.magpie_test_user
        )
        self.magpie.create_permission_by_user_and_res_id(self.magpie_test_user, self.layer_id, {
            "permission": {
                "name": layer_read_permission.name,
                "access": layer_read_permission.access,
                "scope": layer_read_permission.scope
            }})
        self.geoserver.permission_created(layer_read_permission)
        utils.check_mock_has_calls_exactly(self.mock_chown, self.expected_chown_shapefile_calls)
        for file in self.shapefile_list:
            utils.check_file_permissions(file, 0o500)

        # If a file is missing, an update from Magpie's permissions should not trigger an error,
        # the missing file is simply ignored.
        os.remove(self.datastore_path + f"/{self.test_shapefile_name}.shp")
        self.geoserver.permission_created(layer_read_permission)

    def apply_and_check_recursive_permissions(self, resource_id, resource_name):
        # Initialize workspace as read-only
        os.chmod(self.datastore_path, 0o500)
        self.magpie.create_permission_by_user_and_res_id(self.magpie_test_user, self.workspace_res_id, {
            "permission": {
                "name": "describefeaturetype",
                "access": "allow",
                "scope": "match"
            }})
        # Update resource with recursive write permissions
        recursive_write_permission = Permission(
            service_name="geoserver",
            resource_id=resource_id,
            resource_full_name=resource_name,
            name="createstoredquery",
            access="allow",
            scope="recursive",
            user=self.magpie_test_user
        )
        self.magpie.create_permission_by_user_and_res_id(self.magpie_test_user, resource_id, {
            "permission": {
                "name": recursive_write_permission.name,
                "access": recursive_write_permission.access,
                "scope": recursive_write_permission.scope}})

        self.geoserver.permission_created(recursive_write_permission)

        utils.check_mock_has_calls_exactly(self.mock_chown, [mock.call(self.datastore_path, DEFAULT_UID, DEFAULT_GID)] +
                                           self.expected_chown_shapefile_calls)
        utils.check_file_permissions(self.datastore_path, 0o700)
        for file in self.shapefile_list:
            utils.check_file_permissions(file, 0o200)

        # Delete a permission on Magpie
        self.magpie.delete_permission_by_user_and_res_id(self.magpie_test_user, resource_id,
                                                         recursive_write_permission.name)
        self.geoserver.permission_deleted(recursive_write_permission)
        utils.check_mock_has_calls_exactly(self.mock_chown, [mock.call(self.datastore_path, DEFAULT_UID, DEFAULT_GID)] +
                                           self.expected_chown_shapefile_calls)
        utils.check_file_permissions(self.datastore_path, 0o500)
        for file in self.shapefile_list:
            utils.check_file_permissions(file, 0o000)

    def test_magpie_workspace_permission(self):
        self.apply_and_check_recursive_permissions(self.workspace_res_id, f"/geoserver/{self.workspace_name}")

    def test_magpie_service_permission(self):
        self.apply_and_check_recursive_permissions(self.test_service_id, "/geoserver")
