import mock
import pytest

from cowbird import constants as c


@pytest.mark.utils
def test_get_constant_with_same_name():
    # TODO: Not so sure of the intention of this test, was using COWBIRD_URL, but obviously COWBIRD_URL is override
    #  from settings and test failed.  COWBIRD_ROOT is in COWBIRD_CONSTANTS and not overridable so now it works.
    test_value = "test-constant"
    c.COWBIRD_ROOT = test_value
    value = c.get_constant("COWBIRD_ROOT")
    assert value == test_value


@pytest.mark.utils
def test_get_constant_with_settings():
    settings = {
        "cowbird.test_some_value": "some-value",
        "COWBIRD_TEST_ANOTHER": "another-value",
    }
    assert c.get_constant("COWBIRD_TEST_ANOTHER", settings) == settings["COWBIRD_TEST_ANOTHER"]
    assert c.get_constant("cowbird.test_some_value", settings) == settings["cowbird.test_some_value"]


@pytest.mark.utils
def test_get_constant_alternative_name():
    settings = {"cowbird.test_some_value": "some-value"}
    assert c.get_constant("COWBIRD_TEST_SOME_VALUE", settings) == settings["cowbird.test_some_value"]


@pytest.mark.utils
def test_get_constant_raise_missing_when_requested():
    with pytest.raises(LookupError):
        c.get_constant("COWBIRD_DOESNT_EXIST", raise_missing=True)

    try:
        value = c.get_constant("COWBIRD_DOESNT_EXIST", raise_missing=False)
        assert value is None
    except LookupError:
        pytest.fail(msg="Should not have raised although constant is missing.")


@pytest.mark.utils
def test_get_constant_raise_not_set_when_requested():
    settings = {"cowbird.not_set_but_exists": None}
    with pytest.raises(ValueError):
        c.get_constant("COWBIRD_NOT_SET_BUT_EXISTS", settings, raise_not_set=True)
    with pytest.raises(ValueError):
        c.get_constant("cowbird.not_set_but_exists", settings, raise_not_set=True)

    try:
        value = c.get_constant("COWBIRD_NOT_SET_BUT_EXISTS", settings, raise_not_set=False)
        assert value is None
    except LookupError:
        pytest.fail(msg="Should not have raised although constant is not set.")
    try:
        value = c.get_constant("cowbird.not_set_but_exists", settings, raise_not_set=False)
        assert value is None
    except LookupError:
        pytest.fail(msg="Should not have raised although constant is not set.")


@pytest.mark.utils
def test_constant_prioritize_setting_before_env_when_specified():
    settings = {"cowbird.some_existing_var": "FROM_SETTING"}
    override = {"COWBIRD_SOME_EXISTING_VAR": "FROM_ENV"}
    with mock.patch.dict("os.environ", override):
        var = c.get_constant("COWBIRD_SOME_EXISTING_VAR", settings)
        assert var == settings["cowbird.some_existing_var"]
        var = c.get_constant("COWBIRD_SOME_EXISTING_VAR")
        assert var == override["COWBIRD_SOME_EXISTING_VAR"]


@pytest.mark.utils
def test_constant_protected_no_override():
    for const_name in c.COWBIRD_CONSTANTS:
        with mock.patch.dict("os.environ", {const_name: "override-value"}):
            const = c.get_constant(const_name)
            assert const != "override-value"
