import pytest
from pydantic import SecretStr

from procurement_platform.bootstrap.settings import (
    FeishuSettings,
    NotificationGatewaySettings,
    Settings,
)


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
    assert settings.llm_enabled is False
    assert settings.fault_knowledge_path == "knowledge/fault-guidance"
    assert settings.fault_state_ttl_seconds == 86400
    assert settings.fault_guidance_enabled is False
    assert "secret" not in repr(settings)


def test_fault_guidance_settings_can_be_overridden() -> None:
    settings = Settings.from_env(
        environment(FAULT_KNOWLEDGE_PATH="custom/knowledge", FAULT_STATE_TTL_SECONDS="120")
    )
    assert settings.fault_knowledge_path == "custom/knowledge"
    assert settings.fault_state_ttl_seconds == 120
    with pytest.raises(ValueError, match="knowledge path"):
        Settings.from_env(environment(FAULT_KNOWLEDGE_PATH=" "))


def test_fault_guidance_requires_llm_and_redis() -> None:
    with pytest.raises(ValueError, match="LLM"):
        Settings.from_env(environment(PROCUREMENT_FAULT_GUIDANCE_ENABLED="true"))
    with pytest.raises(ValueError, match="REDIS_URL"):
        Settings.from_env(
            environment(
                PROCUREMENT_FAULT_GUIDANCE_ENABLED="true",
                PROCUREMENT_LLM_ENABLED="true",
            )
        )
    settings = Settings.from_env(
        environment(
            PROCUREMENT_FAULT_GUIDANCE_ENABLED="true",
            PROCUREMENT_LLM_ENABLED="true",
            PROCUREMENT_REDIS_URL="redis://localhost:6379/0",
        )
    )
    assert settings.fault_guidance_enabled is True


def test_llm_setting_is_explicit_and_strict() -> None:
    assert Settings.from_env(environment(PROCUREMENT_LLM_ENABLED="true")).llm_enabled is True
    with pytest.raises(ValueError, match="boolean"):
        Settings.from_env(environment(PROCUREMENT_LLM_ENABLED="sometimes"))


def test_missing_secret_fails_fast() -> None:
    with pytest.raises(ValueError, match="IDENTITY_GATEWAY_SECRET"):
        Settings.from_env(environment(PROCUREMENT_IDENTITY_GATEWAY_SECRET=""))


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        Settings.from_env(environment(PROCUREMENT_BACKEND_REQUEST_TIMEOUT_SECONDS="0"))


def test_production_rejects_test_platform() -> None:
    with pytest.raises(ValueError, match="production"):
        Settings.from_env(environment(PROCUREMENT_ENVIRONMENT="production"))


def test_feishu_paths_and_required_credentials() -> None:
    with pytest.raises(ValueError, match="absolute path"):
        FeishuSettings(webhook_path="https://example.test/webhook")
    with pytest.raises(ValueError, match="requires"):
        FeishuSettings(enabled=True)
    configured = FeishuSettings(
        enabled=True,
        app_id="app",
        app_secret=SecretStr("secret"),
        verification_token=SecretStr("verify"),
    )
    assert "secret" not in repr(configured)
    assert "verify" not in repr(configured)


def test_production_notification_gateway_requires_token_and_durable_store() -> None:
    with pytest.raises(ValueError, match="bearer token"):
        Settings(
            environment="production",
            service_name="service",
            backend_base_url="http://backend",
            backend_request_timeout_seconds=1,
            identity_gateway_secret=SecretStr("identity"),
            notification_gateway=NotificationGatewaySettings(enabled=True),
        )


def test_production_distributed_state_requires_redis_and_accepts_safe_profile() -> None:
    with pytest.raises(ValueError, match="local conversation lock"):
        Settings.from_env(
            environment(
                PROCUREMENT_ENVIRONMENT="production",
                PROCUREMENT_ALLOW_TEST_PLATFORM="false",
                PROCUREMENT_EVENT_DEDUP_STORE_BACKEND="redis",
                PROCUREMENT_REDIS_URL="redis://:secret@redis:6379/0",
            )
        )

    settings = Settings.from_env(
        environment(
            PROCUREMENT_ENVIRONMENT="production",
            PROCUREMENT_ALLOW_TEST_PLATFORM="false",
            PROCUREMENT_EVENT_DEDUP_STORE_BACKEND="redis",
            PROCUREMENT_CONVERSATION_LOCK_BACKEND="redis",
            PROCUREMENT_REDIS_URL="redis://:secret@redis:6379/0",
        )
    )
    assert settings.conversation_lock_backend == "redis"
    assert "secret" not in repr(settings)
    with pytest.raises(ValueError, match="memory"):
        Settings(
            environment="production",
            service_name="service",
            backend_base_url="http://backend",
            backend_request_timeout_seconds=1,
            identity_gateway_secret=SecretStr("identity"),
            notification_gateway=NotificationGatewaySettings(
                enabled=True, bearer_token=SecretStr("token")
            ),
        )
