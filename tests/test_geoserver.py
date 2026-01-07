# pylint: disable=protected-access
"""
These tests require a working Geoserver instance.

They can be run with the `Make test-geoserver` target.
More integration tests should be in Jupyter Notebook format as is the case with Birdhouse-deploy / DACCS platform.
"""
import glob
import logging
import os
import shutil
from pathlib import Path
from typing import List, Tuple, cast

import mock
import pytest
import yaml
from dotenv import load_dotenv
from magpie.permissions import Access
from magpie.permissions import Permission as MagpiePermission
from magpie.permissions import Scope
from magpie.services import ServiceGeoserver

from cowbird.constants import COWBIRD_ROOT, DEFAULT_ADMIN_GID, DEFAULT_ADMIN_UID
from cowbird.handlers import HandlerFactory
from cowbird.handlers.impl.geoserver import SHAPEFILE_MAIN_EXTENSION, Geoserver, GeoserverError
from cowbird.handlers.impl.magpie import GEOSERVER_READ_PERMISSIONS, GEOSERVER_WRITE_PERMISSIONS, MagpieHttpError
from cowbird.permissions_synchronizer import Permission
from cowbird.typedefs import JSON
from tests import utils

CURR_DIR = Path(__file__).resolve().parent


def get_geoserver_settings():
    """
    Setup basic parameters for an unmodified local test run (using the example files) unless environment variables are
    set.
    """
    load_dotenv(CURR_DIR / "../docker/.env.example")
    config_path = os.path.join(COWBIRD_ROOT, "config/config.example.yml")

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


def prepare_geoserver_test_workspace(test_instance: "TestGeoserver",
                                     geoserver_handler: Geoserver,
                                     workspace_key: str,
                                     ) -> Tuple[str, str]:
    """
    Prepares a workspace, its datastore and a test shapefile along with the associated Geoserver resources.
    """
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
    if not datastore_path.startswith("/tmp/"):
        raise PermissionError("Aborting test workspace preparation. The test datastore path should be in the `/tmp`"
                              f"directory, but was instead found at the path `{datastore_path}`.")

    # This next part can fail if the user running this test doesn't have write access to the directory
    copy_shapefile(basename=test_instance.test_shapefile_name, destination=datastore_path)

    return workspace_name, datastore_name


def reset_geoserver_test_workspace(test_instance, geoserver_handler):
    """
    Removes a workspace on the file system and the associated resources on Geoserver.
    """
    for _, workspace in test_instance.workspaces.items():
        try:
            geoserver_handler._remove_workspace_request(workspace_name=workspace)
        except GeoserverError:
            # Making sure all test workspaces are removed
            pass
    for _, folder in test_instance.workspace_folders.items():
        try:
            if not folder.startswith("/tmp/"):
                raise PermissionError("Aborting test workspace reset. The test workspace path should be in the `/tmp`"
                                      f"directory, but was instead found at the path `{folder}`.")
            # Make sure access permissions are enabled before deleting files
            os.chmod(folder, 0o777)
            for root, dirs, files in os.walk(folder):
                for resource in dirs + files:
                    os.chmod(os.path.join(root, resource), 0o777)
            shutil.rmtree(folder)
        except FileNotFoundError:
            pass


def copy_shapefile(basename: str, destination: str) -> None:
    full_filename = f"{COWBIRD_ROOT}/tests/resources/{basename}"
    Path(destination).mkdir(parents=True, exist_ok=False)
    for file in glob.glob(f"{full_filename}.*"):
        shutil.copy(file, destination)


def get_datastore_path(workspace_path: str) -> str:
    return workspace_path + "/shapefile_datastore"


class TestGeoserver:
    geoserver_settings = get_geoserver_settings()
    workspaces = {}
    workspace_folders = {}

    test_shapefile_name = "Espace_Vert"

    def teardown_class(self):
        # Couldn't pass fixture to teardown function.
        teardown_gs = Geoserver(settings={}, name="Geoserver", **self.geoserver_settings)
        teardown_gs.ssl_verify = self.geoserver_settings["ssl_verify"]
        reset_geoserver_test_workspace(self, teardown_gs)
        utils.clear_handlers_instances()

    @staticmethod
    def get_geoserver():
        geoserver = Geoserver(settings={}, name="Geoserver", **TestGeoserver.geoserver_settings)
        geoserver.ssl_verify = TestGeoserver.geoserver_settings["ssl_verify"]
        return geoserver


@pytest.mark.geoserver
@pytest.mark.online
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
    # Be careful of typos or path choices, as the paths contained in the following dictionary
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

    def test_workspace_creation(self, geoserver: Geoserver) -> None:
        response = geoserver._create_workspace_request(workspace_name=self.workspaces["creation"])
        assert response.status_code == 201

    def test_empty_workspace_removal(self, geoserver: Geoserver) -> None:
        geoserver._create_workspace_request(workspace_name=self.workspaces["empty-remove"])
        response = geoserver._remove_workspace_request(workspace_name=self.workspaces["empty-remove"])
        assert response.status_code == 200

    def test_duplicate_workspace(self, geoserver: Geoserver) -> None:
        response = geoserver._create_workspace_request(workspace_name=self.workspaces["creation-duplicate"])
        assert response.status_code == 201
        response = geoserver._create_workspace_request(workspace_name=self.workspaces["creation-duplicate"])
        assert response.status_code == 401

    def test_workspace_removal(self, geoserver: Geoserver) -> None:
        geoserver._create_workspace_request(workspace_name=self.workspaces["remove"])
        geoserver._create_datastore_request(workspace_name=self.workspaces["remove"],
                                            datastore_name="test-datastore")
        response = geoserver._remove_workspace_request(workspace_name=self.workspaces["remove"])
        assert response.status_code == 200

    def test_datastore_creation(self, geoserver: Geoserver) -> None:
        geoserver._create_workspace_request(workspace_name=self.workspaces["datastore-create"])
        response = geoserver._create_datastore_request(workspace_name=self.workspaces["datastore-create"],
                                                       datastore_name="test-datastore")
        assert response.status_code == 201

    def test_datastore_creation_missing_workspace(self, geoserver: Geoserver) -> None:
        with pytest.raises(GeoserverError) as error:
            geoserver._create_datastore_request(workspace_name="test-nonexistent-workspace",
                                                datastore_name="test-datastore")
        assert "Operation [_create_datastore_request] failed" in str(error.value)

    def test_datastore_configuration(self, geoserver: Geoserver) -> None:
        geoserver._create_workspace_request(workspace_name=self.workspaces["datastore-config"])
        geoserver._create_datastore_request(workspace_name=self.workspaces["datastore-config"],
                                            datastore_name="test-datastore")

        response = geoserver._configure_datastore_request(workspace_name=self.workspaces["datastore-config"],
                                                          datastore_name="test-datastore",
                                                          datastore_path=geoserver.workspace_dir)
        assert response.status_code == 200

    def test_duplicate_datastore(self, geoserver: Geoserver) -> None:
        geoserver._create_workspace_request(workspace_name=self.workspaces["datastore-duplicate"])
        response = geoserver._create_datastore_request(workspace_name=self.workspaces["datastore-duplicate"],
                                                       datastore_name="test-datastore")
        assert response.status_code == 201

        with pytest.raises(GeoserverError) as error:
            geoserver._create_datastore_request(workspace_name=self.workspaces["datastore-duplicate"],
                                                datastore_name="test-datastore")
        assert "Operation [_create_datastore_request] failed" in str(error.value)

    def test_publish_and_remove_shapefile(self, geoserver: Geoserver) -> None:
        workspace_name, datastore_name = prepare_geoserver_test_workspace(self, geoserver, "publish_remove")

        # Validate and publish shapefile
        geoserver.validate_shapefile(workspace_name=workspace_name, shapefile_name=self.test_shapefile_name)
        response = geoserver._publish_shapefile_request(workspace_name=workspace_name,
                                                        datastore_name=datastore_name,
                                                        filename=self.test_shapefile_name)
        assert response.status_code == 201

        # Remove shapefile
        response = geoserver._remove_shapefile_request(workspace_name=workspace_name,
                                                       datastore_name=datastore_name,
                                                       filename=self.test_shapefile_name)
        assert response.status_code == 200


# pylint: disable=W0201
@pytest.mark.geoserver
@pytest.mark.magpie
@pytest.mark.online
class TestGeoserverPermissions(TestGeoserver):
    """
    Test cases to validate the synchronization between Magpie permissions and file permissions in a Geoserver workspace.

    See :ref:`Components - Geoserver <components_geoserver>` for more details on the design/implementation choices.
    """
    def setup_class(self):
        self.magpie_test_user = "test_user"
        self.magpie_test_group = "users"
        self.workspace_name = self.magpie_test_user

        self.workspaces = {self.magpie_test_user: self.magpie_test_user}
        self.workspace_folders = {
            self.magpie_test_user: f"{TestGeoserver.geoserver_settings['workspace_dir']}/{self.workspace_name}"
        }

        self.datastore_path = get_datastore_path(self.workspace_folders[self.magpie_test_user])

        # Mock the chown function to avoid fail in case the tests are run as non-root
        self.patcher = mock.patch("os.chown")
        self.mock_chown = self.patcher.start()

    def teardown_class(self):
        self.patcher.stop()
        TestGeoserver.teardown_class(self)

    @pytest.fixture(autouse=True)
    def setup(self, tmpdir):
        self.cfg_filepath = tmpdir.strpath + "/test.cfg"
        with open(self.cfg_filepath, "w", encoding="utf-8") as f:
            f.write(yaml.safe_dump({
                "handlers": {
                    "Magpie": {
                        "active": True,
                        "url": os.getenv("COWBIRD_TEST_MAGPIE_URL"),
                        "admin_user": os.getenv("MAGPIE_ADMIN_USER"),
                        "admin_password": os.getenv("MAGPIE_ADMIN_PASSWORD")
                    }}}))

        # Reset handlers instances in case any are left from other test cases
        utils.clear_handlers_instances()

        # Set environment variables with config
        utils.get_test_app(settings={"cowbird.config_path": self.cfg_filepath})

        # Recreate new magpie handler instance with new config
        self.magpie = HandlerFactory().create_handler("Magpie")

        # Reset test user
        self.magpie.delete_user(self.magpie_test_user)
        self.magpie.create_user(self.magpie_test_user, "test@test.com", "qwertyqwerty", self.magpie_test_group)

        # Reset geoserver service
        self.magpie.delete_service("geoserver")
        data = {
            "service_name": "geoserver",
            "service_type": ServiceGeoserver.service_type,
            "service_url": "http://localhost:9000/geoserver",
        }
        self.test_service_id = self.magpie.create_service(data)

        self.geoserver = TestGeoserver.get_geoserver()

        # Setup workspace files
        prepare_geoserver_test_workspace(self, self.geoserver, self.magpie_test_user)
        self.shapefile_list = [
            f for f in self.geoserver.get_shapefile_list(self.workspace_name, self.test_shapefile_name)
            if os.path.exists(f)
        ]

        # Initialize workspace folder with all permissions and shapefile permissions with no permissions for a generic
        # setup, but each test can adjust the permissions for specific cases. Note that permissions are only changed for
        # `others` since the user of the workspace is different than the admin user who is the owner of the files.
        os.chmod(self.datastore_path, 0o777)
        for file in self.shapefile_list:
            os.chmod(file, 0o660)

        # Setup resources
        self.layer_id = self.magpie.get_geoserver_layer_res_id(self.workspace_name, self.test_shapefile_name,
                                                               create_if_missing=True)
        parents_tree = self.magpie.get_parents_resource_tree(self.layer_id)
        self.workspace_res_id = cast(int, parents_tree[-1]["parent_id"])

        self.expected_chown_shapefile_calls = [
            mock.call(file, DEFAULT_ADMIN_UID, DEFAULT_ADMIN_GID) for file in self.shapefile_list
        ]
        self.expected_chown_datastore_call = [mock.call(self.datastore_path, DEFAULT_ADMIN_UID, DEFAULT_ADMIN_GID)]
        yield
        # Teardown
        reset_geoserver_test_workspace(self, self.geoserver)
        self.magpie.delete_user(self.magpie_test_user)
        self.magpie.delete_service("geoserver")

    def check_magpie_permissions(self, res_id, expected_perms, expected_access=Access.ALLOW.value,
                                 expected_scope=Scope.MATCH.value, effective=True):
        """
        Checks if a resource has the expected permissions on Magpie for a specific access and scope value.
        """
        user_permissions = self.magpie.get_user_permissions_by_res_id(self.magpie_test_user,
                                                                      res_id,
                                                                      effective=effective)
        assert set(expected_perms) == {p["name"] for p in cast(List[JSON], user_permissions["permissions"])
                                       if p["access"] == expected_access and p["scope"] == expected_scope
                                       and p["name"] in GEOSERVER_READ_PERMISSIONS + GEOSERVER_WRITE_PERMISSIONS}

    def test_shapefile_on_created(self):
        """
        Tests if the right Magpie permissions are created upon a shapefile creation in a Geoserver workspace.
        """
        # For this test, remove workspace resource and check if required resources are recreated
        self.magpie.delete_resource(self.workspace_res_id)

        for file in self.shapefile_list:
            os.chmod(file, 0o664)
        self.geoserver.on_created(os.path.join(self.datastore_path,
                                               self.test_shapefile_name + SHAPEFILE_MAIN_EXTENSION))

        # File permissions should still be the same.
        for file in self.shapefile_list:
            utils.check_path_permissions(file, 0o664)

        geoserver_resources = self.magpie.get_resources_by_service("geoserver")
        workspace_res = list(geoserver_resources["resources"].values())[0]
        layer_res_id = list(workspace_res["children"])[0]

        # Check if the user has the right permissions on Magpie
        self.check_magpie_permissions(layer_res_id, set(GEOSERVER_READ_PERMISSIONS), expected_access=Access.ALLOW.value)
        self.check_magpie_permissions(layer_res_id, set(GEOSERVER_WRITE_PERMISSIONS), expected_access=Access.DENY.value)
        utils.check_mock_has_calls(self.mock_chown, self.expected_chown_shapefile_calls)

    def test_shapefile_on_modified(self):
        """
        Tests if the right Magpie permissions are updated upon a shapefile permission modification in a Geoserver
        workspace.
        """
        main_shapefile_path = os.path.join(self.datastore_path, self.test_shapefile_name + SHAPEFILE_MAIN_EXTENSION)
        os.chmod(main_shapefile_path, 0o666)

        # Add some specific permissions on the parent service, to test other specific use cases.
        self.magpie.create_permission_by_user_and_res_id(user_name=self.magpie_test_user,
                                                         res_id=self.test_service_id,
                                                         perm_name=MagpiePermission.DESCRIBE_FEATURE_TYPE.value,
                                                         perm_access=Access.ALLOW.value,
                                                         perm_scope=Scope.RECURSIVE.value)
        self.magpie.create_permission_by_user_and_res_id(user_name=self.magpie_test_user,
                                                         res_id=self.test_service_id,
                                                         perm_name=MagpiePermission.DESCRIBE_LAYER.value,
                                                         perm_access=Access.DENY.value,
                                                         perm_scope=Scope.RECURSIVE.value)

        self.geoserver.on_modified(main_shapefile_path)

        # `Allow` permissions should have been created for all read/write permissions, except for the one permission
        # added above to the service. No permission is required on the resource since it already resolves as `Allow`.
        self.check_magpie_permissions(self.layer_id, set(GEOSERVER_READ_PERMISSIONS + GEOSERVER_WRITE_PERMISSIONS))
        self.check_magpie_permissions(self.layer_id,
                                      [p for p in GEOSERVER_READ_PERMISSIONS + GEOSERVER_WRITE_PERMISSIONS
                                       if p != MagpiePermission.DESCRIBE_FEATURE_TYPE.value],
                                      effective=False)
        utils.check_mock_has_calls(self.mock_chown, self.expected_chown_shapefile_calls)

        os.chmod(main_shapefile_path, 0o660)
        self.geoserver.on_modified(main_shapefile_path)

        # All read/write permissions should have no permissions now, since it resolves automatically to `Deny` if no
        # permission is present. The only exception is the one permission which was allowed recursively on the service,
        # which now requires a specific `Deny` permission on the layer.
        self.check_magpie_permissions(self.layer_id, set(GEOSERVER_READ_PERMISSIONS + GEOSERVER_WRITE_PERMISSIONS),
                                      expected_access=Access.DENY.value)
        self.check_magpie_permissions(self.layer_id, [MagpiePermission.DESCRIBE_FEATURE_TYPE.value],
                                      expected_access=Access.DENY.value, effective=False)
        self.check_magpie_permissions(self.layer_id, [], expected_access=Access.ALLOW.value, effective=False)
        utils.check_mock_has_calls(self.mock_chown, self.expected_chown_shapefile_calls)

    def test_shapefile_on_modified_other_ext(self):
        """
        Tests modification events on any other file of the shapefile that does not have the main extension (.shp), which
        should not trigger any other event or modification.
        """
        other_shapefile_path = os.path.join(self.datastore_path, self.test_shapefile_name + ".shx")
        os.chmod(other_shapefile_path, 0o666)
        self.geoserver.on_modified(other_shapefile_path)

        for file in self.shapefile_list:
            if file.endswith(".shx"):
                utils.check_path_permissions(file, 0o666)
            else:
                utils.check_path_permissions(file, 0o660)
        self.check_magpie_permissions(self.layer_id, set(GEOSERVER_READ_PERMISSIONS + GEOSERVER_WRITE_PERMISSIONS),
                                      expected_access=Access.DENY.value)
        self.check_magpie_permissions(self.layer_id, [], expected_access=Access.DENY.value, effective=False)

    def test_shapefile_on_deleted(self):
        """
        Tests if the right Magpie permissions are deleted upon a shapefile removal in a Geoserver workspace.
        """
        self.geoserver.on_deleted(self.datastore_path + f"/{self.test_shapefile_name}.shp")
        for file in self.shapefile_list:
            assert not os.path.exists(file)

        # Check that magpie layer resource was removed
        with pytest.raises(MagpieHttpError):
            self.magpie.get_user_permissions_by_res_id(self.magpie_test_user, self.layer_id)

    def test_workspace_on_created(self):
        # For this test, remove workspace resource and check if required resources are recreated
        self.magpie.delete_resource(self.workspace_res_id)

        # No Magpie resources should be created if only a created folder event is triggered
        self.geoserver.on_created(os.path.join(self.datastore_path))
        geoserver_resources = self.magpie.get_resources_by_service("geoserver")
        assert len(geoserver_resources["resources"]) == 0

        # If a created file event is triggered, the workspace resource should still have no permissions updated.
        os.chmod(self.datastore_path, 0o775)
        self.geoserver.on_created(os.path.join(self.datastore_path,
                                               self.test_shapefile_name + SHAPEFILE_MAIN_EXTENSION))
        geoserver_resources = self.magpie.get_resources_by_service("geoserver")
        workspace_res_id = list(geoserver_resources["resources"])[0]

        # Check if the user has the right permissions on Magpie
        self.check_magpie_permissions(res_id=workspace_res_id, expected_perms=[],
                                      expected_access=Access.DENY.value, expected_scope=Scope.RECURSIVE.value,
                                      effective=False)
        self.check_magpie_permissions(res_id=workspace_res_id, expected_perms=[],
                                      expected_access=Access.ALLOW.value, expected_scope=Scope.RECURSIVE.value,
                                      effective=False)

    def test_workspace_on_modified(self):
        """
        Tests if Magpie resources associated with the user workspace are updated correctly.
        """

        self.magpie.create_permission_by_user_and_res_id(user_name=self.magpie_test_user,
                                                         res_id=self.workspace_res_id,
                                                         perm_name=MagpiePermission.DESCRIBE_LAYER.value,
                                                         perm_access=Access.ALLOW.value,
                                                         perm_scope=Scope.RECURSIVE.value)
        self.magpie.create_permission_by_user_and_res_id(user_name=self.magpie_test_user,
                                                         res_id=self.workspace_res_id,
                                                         perm_name=MagpiePermission.DESCRIBE_STORED_QUERIES.value,
                                                         perm_access=Access.ALLOW.value,
                                                         # This should be reset to `recursive` in modify event.
                                                         perm_scope=Scope.MATCH.value)
        # Add specific permissions on the parent service, to test other specific use cases.
        self.magpie.create_permission_by_user_and_res_id(user_name=self.magpie_test_user,
                                                         res_id=self.test_service_id,
                                                         perm_name=MagpiePermission.DESCRIBE_FEATURE_TYPE.value,
                                                         perm_access=Access.ALLOW.value,
                                                         perm_scope=Scope.RECURSIVE.value)
        self.magpie.create_permission_by_user_and_res_id(user_name=self.magpie_test_user,
                                                         res_id=self.test_service_id,
                                                         perm_name=MagpiePermission.DESCRIBE_STORED_QUERIES.value,
                                                         perm_access=Access.DENY.value,
                                                         perm_scope=Scope.RECURSIVE.value)

        os.chmod(self.datastore_path, 0o775)
        self.geoserver.on_modified(self.datastore_path)

        # All read permissions should be explicitly set to `allow` here, except for the one permission set to `allow`
        # recursively on the parent service resource.
        self.check_magpie_permissions(
            res_id=self.workspace_res_id,
            expected_perms=[p for p in GEOSERVER_READ_PERMISSIONS if p != MagpiePermission.DESCRIBE_FEATURE_TYPE.value],
            expected_access=Access.ALLOW.value,
            expected_scope=Scope.RECURSIVE.value,
            effective=False)
        # No write permission should be explicitly set to `deny` in this case, since they already resolve to `deny`.
        self.check_magpie_permissions(
            res_id=self.workspace_res_id,
            expected_perms=[],
            expected_access=Access.DENY.value,
            expected_scope=Scope.RECURSIVE.value,
            effective=False)
        utils.check_mock_has_calls(self.mock_chown, self.expected_chown_datastore_call)

        os.chmod(self.datastore_path, 0o770)
        self.geoserver.on_modified(self.datastore_path)

        self.check_magpie_permissions(self.workspace_res_id,
                                      set(GEOSERVER_READ_PERMISSIONS + GEOSERVER_WRITE_PERMISSIONS),
                                      expected_access=Access.DENY.value)
        # Only one permission requires an explicit `deny`, because of the `allow` permission on the parent service.
        self.check_magpie_permissions(self.workspace_res_id,
                                      [MagpiePermission.DESCRIBE_FEATURE_TYPE.value],
                                      expected_access=Access.DENY.value,
                                      expected_scope=Scope.RECURSIVE.value,
                                      effective=False)
        self.check_magpie_permissions(self.workspace_res_id, [], expected_access=Access.ALLOW.value, effective=False)
        utils.check_mock_has_calls(self.mock_chown, self.expected_chown_datastore_call)

    def test_workspace_on_deleted(self, caplog):
        """
        Tests if Magpie resources associated with the user workspace are deleted only when a `user_deleted` event is
        triggered.
        """
        # Check that `on_deleted` events do not remove the corresponding Magpie resources, since manual deletion
        # of the workspace should not happen and is not supported.
        self.geoserver.on_deleted("/test_path_from_other_service")
        assert len(caplog.records) == 0
        self.geoserver.on_deleted(self.datastore_path)
        assert len(caplog.records) == 1 and caplog.records[0].levelno == logging.WARNING

        # Check that magpie resource still exists after the `on_deleted` events
        self.magpie.get_resource(self.workspace_res_id)

        # Check that the user workspace magpie resources are deleted after a `user_deleted` event
        self.geoserver.user_deleted(self.magpie_test_user)
        with pytest.raises(MagpieHttpError):
            self.magpie.get_resource(self.workspace_res_id)

    def test_magpie_layer_permissions(self):
        """
        Tests modifications on layer permissions on Magpie and the resulting updates of the permissions on the related
        files.
        """
        # Update shapefile read permissions
        layer_read_permission = Permission(
            service_name="geoserver",
            service_type=ServiceGeoserver.service_type,
            resource_id=self.layer_id,
            resource_full_name=f"/geoserver/{self.workspace_name}/{self.test_shapefile_name}",
            name=MagpiePermission.DESCRIBE_FEATURE_TYPE.value,
            access=Access.ALLOW.value,
            scope=Scope.MATCH.value,
            user=self.magpie_test_user
        )
        self.magpie.create_permission_by_user_and_res_id(
            user_name=self.magpie_test_user,
            res_id=self.layer_id,
            perm_name=layer_read_permission.name,
            perm_access=layer_read_permission.access,
            perm_scope=layer_read_permission.scope)
        self.geoserver.permission_created(layer_read_permission)
        utils.check_mock_has_calls(self.mock_chown, self.expected_chown_shapefile_calls)
        for file in self.shapefile_list:
            utils.check_path_permissions(file, 0o664)

        # If a file is missing, an update from Magpie's permissions should not trigger an error,
        # the missing file is simply ignored.
        os.remove(self.datastore_path + f"/{self.test_shapefile_name}.shx")
        updated_shapefile_list = [f for f in self.shapefile_list if not f.endswith(".shx")]
        updated_chown_checklist = [mock.call(file, DEFAULT_ADMIN_UID, DEFAULT_ADMIN_GID)
                                   for file in updated_shapefile_list]

        # Change access to 'deny'
        self.magpie.delete_permission_by_user_and_res_id(self.magpie_test_user, self.layer_id,
                                                         MagpiePermission.DESCRIBE_FEATURE_TYPE.value)
        layer_deny_permission = Permission(
            service_name="geoserver",
            service_type=ServiceGeoserver.service_type,
            resource_id=self.layer_id,
            resource_full_name=f"/geoserver/{self.workspace_name}/{self.test_shapefile_name}",
            name=MagpiePermission.DESCRIBE_FEATURE_TYPE.value,
            access=Access.DENY.value,
            scope=Scope.MATCH.value,
            user=self.magpie_test_user
        )
        self.magpie.create_permission_by_user_and_res_id(
            user_name=self.magpie_test_user,
            res_id=self.layer_id,
            perm_name=layer_deny_permission.name,
            perm_access=layer_deny_permission.access,
            perm_scope=layer_deny_permission.scope)
        self.geoserver.permission_created(layer_deny_permission)
        utils.check_mock_has_calls(self.mock_chown, updated_chown_checklist)
        for file in updated_shapefile_list:
            utils.check_path_permissions(file, 0o660)

        # Case for a deleted permission on Magpie
        for file in updated_shapefile_list:
            os.chmod(file, 0o664)

        # Remove the existing 'deny' permission
        self.magpie.delete_permission_by_user_and_res_id(self.magpie_test_user, self.layer_id,
                                                         MagpiePermission.DESCRIBE_FEATURE_TYPE.value)
        # Test as if the first 'allow' permission was deleted
        self.geoserver.permission_deleted(layer_read_permission)

        utils.check_mock_has_calls(self.mock_chown, updated_chown_checklist)
        for file in updated_shapefile_list:
            utils.check_path_permissions(file, 0o660)

    def apply_and_check_recursive_permissions(self, resource_id, resource_name):
        """
        Used in different test cases to check the creation and deletion of a recursive permission on Magpie, validating
        if the resource's files and all the children resources' files are updated.
        """
        # Initialize workspace as read-only
        os.chmod(self.datastore_path, 0o775)
        self.magpie.create_permission_by_user_and_res_id(
            user_name=self.magpie_test_user,
            res_id=self.workspace_res_id,
            perm_name=MagpiePermission.DESCRIBE_FEATURE_TYPE.value,
            perm_access=Access.ALLOW.value,
            perm_scope=Scope.MATCH.value)
        # Update resource with recursive write permissions
        recursive_write_permission = Permission(
            service_name="geoserver",
            service_type=ServiceGeoserver.service_type,
            resource_id=resource_id,
            resource_full_name=resource_name,
            name=MagpiePermission.CREATE_STORED_QUERY.value,
            access=Access.ALLOW.value,
            scope=Scope.RECURSIVE.value,
            user=self.magpie_test_user
        )
        self.magpie.create_permission_by_user_and_res_id(
            user_name=self.magpie_test_user,
            res_id=resource_id,
            perm_name=recursive_write_permission.name,
            perm_access=recursive_write_permission.access,
            perm_scope=recursive_write_permission.scope)

        self.geoserver.permission_created(recursive_write_permission)

        utils.check_mock_has_calls(self.mock_chown,
                                   self.expected_chown_datastore_call + self.expected_chown_shapefile_calls)
        utils.check_path_permissions(self.datastore_path, 0o777)
        for file in self.shapefile_list:
            utils.check_path_permissions(file, 0o662)

        # Adding `match` permissions on the layer and changing the recursive permission to `deny`
        # The layer should keep its write permission, but the workspace should lose its write permission.
        self.magpie.create_permission_by_user_and_res_id(
            user_name=self.magpie_test_user,
            res_id=self.layer_id,
            perm_name=MagpiePermission.CREATE_STORED_QUERY.value,
            perm_access=Access.ALLOW.value,
            perm_scope=Scope.MATCH.value)
        self.magpie.delete_permission_by_user_and_res_id(self.magpie_test_user, resource_id,
                                                         recursive_write_permission.name)
        recursive_write_permission.access = Access.DENY.value
        self.magpie.create_permission_by_user_and_res_id(
            user_name=self.magpie_test_user,
            res_id=resource_id,
            perm_name=recursive_write_permission.name,
            perm_access=recursive_write_permission.access,
            perm_scope=recursive_write_permission.scope)
        self.geoserver.permission_created(recursive_write_permission)

        utils.check_mock_has_calls(self.mock_chown,
                                   self.expected_chown_datastore_call + self.expected_chown_shapefile_calls)
        utils.check_path_permissions(self.datastore_path, 0o775)
        for file in self.shapefile_list:
            utils.check_path_permissions(file, 0o662)

        # Delete a permission on Magpie
        self.magpie.delete_permission_by_user_and_res_id(self.magpie_test_user, self.layer_id,
                                                         MagpiePermission.CREATE_STORED_QUERY.value)
        self.magpie.delete_permission_by_user_and_res_id(self.magpie_test_user, resource_id,
                                                         recursive_write_permission.name)
        self.geoserver.permission_deleted(recursive_write_permission)
        utils.check_mock_has_calls(self.mock_chown,
                                   self.expected_chown_datastore_call + self.expected_chown_shapefile_calls)
        utils.check_path_permissions(self.datastore_path, 0o775)
        for file in self.shapefile_list:
            utils.check_path_permissions(file, 0o660)

    def test_magpie_workspace_permission(self):
        """
        Tests modifications on a workspace's recursive permissions on Magpie and the updates of the related files.
        """
        self.apply_and_check_recursive_permissions(self.workspace_res_id, f"/geoserver/{self.workspace_name}")

    def test_magpie_service_permission(self):
        """
        Tests modifications on a service's recursive permissions on Magpie and the updates of the related files.
        """
        self.apply_and_check_recursive_permissions(self.test_service_id, "/geoserver")

    def test_group_permission(self):
        """
        Tests modifications on a resource's group permission, which should not trigger any change to the associated path
        on the file system, since the Geoserver handler does not support groups.
        """
        layer_read_permission = Permission(
            service_name="geoserver",
            service_type=ServiceGeoserver.service_type,
            resource_id=self.layer_id,
            resource_full_name=f"/geoserver/{self.workspace_name}/{self.test_shapefile_name}",
            name=MagpiePermission.DESCRIBE_FEATURE_TYPE.value,
            access=Access.ALLOW.value,
            scope=Scope.MATCH.value,
            group=self.magpie_test_group
        )
        self.magpie.create_permission_by_grp_and_res_id(
            grp_name=layer_read_permission.group,
            res_id=layer_read_permission.resource_id,
            perm_name=layer_read_permission.name,
            perm_access=layer_read_permission.access,
            perm_scope=layer_read_permission.scope)

        # Permission events on groups are not supported by the Geoserver handler.
        with pytest.raises(NotImplementedError):
            self.geoserver.permission_created(layer_read_permission)
