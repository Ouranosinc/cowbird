import mock
import pytest
from cowbird.services.service_factory import ServiceFactory
from tests.utils import TEST_CFG_FILE


@pytest.mark.service_factory
def test_service_factory():
    override = {"COWBIRD_CONFIG_PATH": TEST_CFG_FILE}
    with mock.patch.dict("os.environ", override):
        # Test singleton
        m1 = ServiceFactory().get_service("Magpie")
        m2 = ServiceFactory().get_service("Magpie")
        assert m1 is m2
        assert len(ServiceFactory().services) == 1
        assert ServiceFactory().services["Magpie"] is m1

        # Test services config
        services = ServiceFactory().get_active_services()
        assert services[0].name == "Magpie"
        assert services[1].name == "Geoserver"
        assert services[2].name == "Thredds"
        assert services[3].name == "Nginx"