from pydantic import SecretStr

from procurement_platform.adapters.backend.http_client import HttpBackendClient
from procurement_platform.bootstrap.container import ApplicationContainer
from procurement_platform.bootstrap.settings import FeishuSettings, Settings
from procurement_platform.domain.enums import BackendMode


class _FakeLarkTransport:
    def __init__(self, app_id: str, app_secret: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret


class _FakeLlm:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    async def aclose(self) -> None:
        return None


class _FakeRedis:
    async def eval(self, script: str, numkeys: int, *args: object) -> object:
        del script, numkeys, args
        return 1

    async def get(self, key: str) -> object:
        del key
        return None

    async def set(self, key: str, value: str, *, ex: int) -> object:
        del key, value, ex
        return True

    async def delete(self, key: str) -> object:
        del key
        return 1

    async def expire(self, key: str, seconds: int) -> object:
        del key, seconds
        return True


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


def test_fault_guidance_is_wired_only_when_explicitly_enabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "procurement_platform.bootstrap.container.LarkOapiTransport",
        _FakeLarkTransport,
    )
    monkeypatch.setattr(
        "procurement_platform.bootstrap.container.OpenAICompatibleLlmClient",
        _FakeLlm,
    )
    monkeypatch.setattr(
        "procurement_platform.bootstrap.container._build_redis_client",
        lambda settings: _FakeRedis(),
    )
    settings = Settings(
        environment="test",
        service_name="test-service",
        backend_base_url="http://backend",
        backend_request_timeout_seconds=1,
        identity_gateway_secret=SecretStr("identity"),
        backend_mode=BackendMode.HTTP,
        llm_enabled=True,
        llm_api_key=SecretStr("llm"),
        llm_model="test-model",
        fault_guidance_enabled=True,
        redis_url=SecretStr("redis://localhost:6379/0"),
        feishu=FeishuSettings(
            enabled=True,
            app_id="app",
            app_secret=SecretStr("secret"),
            verification_token=SecretStr("verify"),
        ),
    )

    container = ApplicationContainer.build(settings)

    assert container.fault_guidance_service is not None
    assert container.assistant_service is not None
    assert container.assistant_service._fault_guidance_service is (container.fault_guidance_service)
