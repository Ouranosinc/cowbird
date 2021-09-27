# pylint: disable=protected-access
"""
These tests require a working Geoserver instance.

They are ignored by the `Make test` target and the CI, but are
still useful for a developer working on the Geoserver requests. They can be run with the `Make test-geoserver` target.
More integration tests should be in Jupyter Notebook format as is the case with Birdhouse-deploy / DACCS platform.
"""
import os

import pytest
import yaml

from cowbird.constants import COWBIRD_ROOT
from cowbird.services.impl.geoserver import Geoserver, GeoserverError


def get_geoserver_settings():
    """
    Setup basic parameters for an unmodified local test run (using the example files) unless environment variables are
    set.
    """
    config_path = os.path.join(COWBIRD_ROOT, "config/config.example.yml")
    settings_dictionary = yaml.safe_load(open(config_path, "r"))
    geoserver_settings = settings_dictionary["services"]["Geoserver"]
    if "${HOSTNAME}" in geoserver_settings["url"]:
        hostname = os.getenv("HOSTNAME", "localhost")
        geoserver_settings["url"] = geoserver_settings["url"].replace("${HOSTNAME}", hostname)
    if "${WORKSPACE_DIR}" in geoserver_settings["workspace_dir"]:
        workdir = os.getenv("WORKSPACE_DIR", "/tmp/user_workspace")
        geoserver_settings["workspace_dir"] = geoserver_settings["workspace_dir"].replace("${WORKDIR}", workdir)
    if "${GEOSERVER_ADMIN}" in geoserver_settings["admin_user"]:
        workdir = os.getenv("GEOSERVER_ADMIN", "")
        geoserver_settings["admin_user"] = geoserver_settings["admin_user"].replace("${GEOSERVER_ADMIN}", workdir)
    if "${GEOSERVER_PASSWORD}" in geoserver_settings["admin_password"]:
        workdir = os.getenv("GEOSERVER_PASSWORD", "")
        geoserver_settings["admin_password"] = geoserver_settings["admin_password"].replace("${GEOSERVER_PASSWORD}",
                                                                                            workdir)
    geoserver_settings["ssl_verify"] = os.getenv("COWBIRD_SSL_VERIFY", False)
    return geoserver_settings


@pytest.mark.geoserver
class TestGeoserverRequests:
    workspaces = {
        "creation": "test-workspace-creation",
        "creation-duplicate": "test-duplicate-workspace",
        "empty-remove": "test-empty-workspace-removal",
        "remove": "test-workspace-removal",
        "datastore-create": "test-datastore-creation",
        "datastore-config": "test-datastore-configuration",
        "datastore-duplicate": "test-duplicate-datastore"
    }
    geoserver_settings = get_geoserver_settings()

    @pytest.fixture
    def geoserver(self):
        # Bypasses ServiceFactory() to prevent side effects in other tests.
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
        with pytest.raises(GeoserverError) as error:
            geoserver._create_workspace_request(workspace_name=self.workspaces["creation-duplicate"])
        assert "Geoserver workspace already exists" in str(error.value)

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
