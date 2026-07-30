from pydantic import SecretStr

from procurement_platform.adapters.backend.http_client import HttpBackendClient
from procurement_platform.bootstrap.container import ApplicationContainer
from procurement_platform.bootstrap.settings import FeishuSettings, Settings
from procurement_platform.domain.enums import BackendMode


class _FakeLarkTransport:
    def __init__(self, app_id: str, app_secret: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret


def test_http_mode_injects_real_backend_client_into_message_handler(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "procurement_platform.bootstrap.container.LarkOapiTransport",
        _FakeLarkTransport,
    )
    settings = Settings(
        environment="test",
        service_name="test-service",
        backend_base_url="http://backend",
        backend_request_timeout_seconds=1,
        identity_gateway_secret=SecretStr("identity"),
        backend_mode=BackendMode.HTTP,
        feishu=FeishuSettings(
            enabled=True,
            app_id="app",
            app_secret=SecretStr("secret"),
            verification_token=SecretStr("verify"),
        ),
    )

    container = ApplicationContainer.build(settings)

    assert isinstance(container.backend_client, HttpBackendClient)
    assert container.message_handler is not None
    assert container.message_handler._backend_client is container.backend_client
