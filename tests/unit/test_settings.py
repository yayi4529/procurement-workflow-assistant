import pytest

from procurement_platform.bootstrap.settings import Settings


def environment(**overrides: str) -> dict[str, str]:
    values = {
        "PROCUREMENT_ENVIRONMENT": "development",
        "PROCUREMENT_SERVICE_NAME": "service",
        "PROCUREMENT_BACKEND_BASE_URL": "http://backend",
        "PROCUREMENT_BACKEND_REQUEST_TIMEOUT_SECONDS": "10",
        "PROCUREMENT_IDENTITY_GATEWAY_SECRET": "secret",
        "PROCUREMENT_ALLOW_TEST_PLATFORM": "true",
    }
    values.update(overrides)
    return values


def test_settings_load_and_hide_secret() -> None:
    settings = Settings.from_env(environment())
    assert settings.backend_request_timeout_seconds == 10
    assert "secret" not in repr(settings)


def test_missing_secret_fails_fast() -> None:
    with pytest.raises(ValueError, match="IDENTITY_GATEWAY_SECRET"):
        Settings.from_env(environment(PROCUREMENT_IDENTITY_GATEWAY_SECRET=""))


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        Settings.from_env(environment(PROCUREMENT_BACKEND_REQUEST_TIMEOUT_SECONDS="0"))


def test_production_rejects_test_platform() -> None:
    with pytest.raises(ValueError, match="production"):
        Settings.from_env(environment(PROCUREMENT_ENVIRONMENT="production"))
