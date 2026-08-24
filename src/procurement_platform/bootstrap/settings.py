import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from pydantic import SecretStr

from procurement_platform.domain.enums import BackendMode


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("boolean setting must be true or false")


def _validate_route_path(value: str) -> None:
    parsed = urlsplit(value)
    if (
        not value.startswith("/")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "route path must be an absolute path without scheme, host, query, or fragment"
        )


@dataclass(frozen=True, slots=True)
class FeishuSettings:
    enabled: bool = False
    app_id: str = ""
    app_secret: SecretStr = field(default_factory=lambda: SecretStr(""), repr=False)
    verification_token: SecretStr = field(default_factory=lambda: SecretStr(""), repr=False)
    encrypt_key: SecretStr | None = field(default=None, repr=False)
    webhook_path: str = "/webhooks/feishu"

    def __post_init__(self) -> None:
        _validate_route_path(self.webhook_path)
        if self.enabled and (
            not self.app_id
            or not self.app_secret.get_secret_value()
            or not self.verification_token.get_secret_value()
        ):
            raise ValueError(
                "enabled Feishu integration requires app_id, app_secret, and verification_token"
            )


@dataclass(frozen=True, slots=True)
class NotificationGatewaySettings:
    enabled: bool = False
    path: str = "/internal/notifications"
    bearer_token: SecretStr | None = field(default=None, repr=False)
    delivery_store_backend: str = "memory"

    def __post_init__(self) -> None:
        _validate_route_path(self.path)
        if self.delivery_store_backend not in {"memory", "redis"}:
            raise ValueError("unsupported notification delivery store backend")


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    service_name: str
    backend_base_url: str
    backend_request_timeout_seconds: float
    identity_gateway_secret: SecretStr = field(repr=False)
    backend_mode: BackendMode = BackendMode.HTTP
    fake_data_path: str = ".local/fake-users.json"
    llm_enabled: bool = False
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = field(default=None, repr=False)
    llm_model: str | None = None
    llm_timeout_seconds: float = 30.0
    llm_max_tool_steps: int = 6
    llm_max_total_tool_calls: int = 24
    llm_max_history_messages: int = 20
    llm_max_tool_result_chars: int = 20000
    llm_context_knowledge_path: str | None = None
    llm_role_skills_path: str | None = "skills"
    llm_skill_routing_mode: str = "strict"
    allow_test_platform: bool = False
    event_dedup_store_backend: str = "memory"
    conversation_lock_backend: str = "local"
    redis_url: SecretStr | None = field(default=None, repr=False)
    redis_timeout_seconds: float = 2.0
    event_dedup_ttl_seconds: int = 86400
    conversation_lock_ttl_seconds: int = 60
    conversation_lock_acquire_timeout_seconds: float = 5.0
    notification_delivery_ttl_seconds: int = 604800
    fault_knowledge_path: str = "knowledge/fault-guidance"
    fault_state_ttl_seconds: int = 86400
    fault_guidance_enabled: bool = False
    debug_identity_probe_enabled: bool = False
    development_notification_renderer_enabled: bool = False
    log_level: str = "INFO"
    log_format: str = "text"
    feishu: FeishuSettings = field(default_factory=FeishuSettings)
    notification_gateway: NotificationGatewaySettings = field(
        default_factory=NotificationGatewaySettings
    )

    def __post_init__(self) -> None:
        environment = self.environment.lower()
        if environment not in {"development", "test", "production"}:
            raise ValueError("environment must be development, test, or production")
        if self.backend_request_timeout_seconds <= 0:
            raise ValueError("backend request timeout must be greater than zero")
        if (
            self.llm_timeout_seconds <= 0
            or self.llm_max_tool_steps < 1
            or self.llm_max_total_tool_calls < 1
        ):
            raise ValueError("invalid LLM timeout or tool step limit")
        if self.llm_max_history_messages < 1 or self.llm_max_tool_result_chars < 2:
            raise ValueError("invalid LLM history or tool result limit")
        if self.llm_skill_routing_mode not in {"off", "hybrid", "strict"}:
            raise ValueError("LLM skill routing mode must be off, hybrid, or strict")
        if not self.identity_gateway_secret.get_secret_value():
            raise ValueError("identity gateway secret is required")
        if self.event_dedup_store_backend not in {"memory", "redis"}:
            raise ValueError("unsupported event dedup store backend")
        if self.conversation_lock_backend not in {"local", "redis"}:
            raise ValueError("unsupported conversation lock backend")
        if self.redis_timeout_seconds <= 0:
            raise ValueError("redis timeout must be greater than zero")
        if not self.fault_knowledge_path.strip():
            raise ValueError("fault knowledge path must not be empty")
        if self.fault_guidance_enabled and not self.llm_enabled:
            raise ValueError("fault guidance requires the LLM to be enabled")
        if (
            min(
                self.event_dedup_ttl_seconds,
                self.conversation_lock_ttl_seconds,
                self.notification_delivery_ttl_seconds,
                self.fault_state_ttl_seconds,
            )
            < 1
        ):
            raise ValueError("redis TTL values must be positive")
        if self.conversation_lock_acquire_timeout_seconds <= 0:
            raise ValueError("conversation lock acquire timeout must be greater than zero")
        if self.log_format not in {"text", "json"}:
            raise ValueError("log format must be text or json")
        if self.backend_mode is BackendMode.FAKE and environment == "production":
            raise ValueError("fake backend is forbidden in production")
        if environment == "production" and self.allow_test_platform:
            raise ValueError("TEST_PLATFORM cannot be enabled in production")
        if environment == "production" and self.debug_identity_probe_enabled:
            raise ValueError("debug identity probe is forbidden in production")
        if environment == "production" and self.development_notification_renderer_enabled:
            raise ValueError("development notification renderer is forbidden in production")
        if environment == "production" and self.notification_gateway.enabled:
            token = self.notification_gateway.bearer_token
            if token is None or not token.get_secret_value():
                raise ValueError("notification gateway bearer token is required in production")
            if self.notification_gateway.delivery_store_backend == "memory":
                raise ValueError("memory notification delivery store is forbidden in production")
        if environment == "production" and self.event_dedup_store_backend == "memory":
            raise ValueError("memory event dedup store is forbidden in production")
        if environment == "production" and self.conversation_lock_backend == "local":
            raise ValueError("local conversation lock is forbidden in production")
        redis_required = (
            self.event_dedup_store_backend == "redis"
            or self.conversation_lock_backend == "redis"
            or self.notification_gateway.delivery_store_backend == "redis"
            or self.fault_guidance_enabled
        )
        if redis_required and (self.redis_url is None or not self.redis_url.get_secret_value()):
            raise ValueError("Redis-backed stores require PROCUREMENT_REDIS_URL")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ
        backend_mode = BackendMode(
            values.get("PROCUREMENT_BACKEND_MODE", BackendMode.HTTP.value).strip().lower()
        )

        def required(name: str) -> str:
            value = values.get(name, "").strip()
            if not value:
                raise ValueError(f"required setting {name} is missing")
            return value

        encrypt_key = values.get("PROCUREMENT_FEISHU_ENCRYPT_KEY", "").strip()
        gateway_token = values.get("PROCUREMENT_NOTIFICATION_GATEWAY_TOKEN", "").strip()
        llm_api_key = values.get("PROCUREMENT_LLM_API_KEY", "").strip()
        llm_base_url = values.get("PROCUREMENT_LLM_BASE_URL", "").strip()
        llm_model = values.get("PROCUREMENT_LLM_MODEL", "").strip()
        return cls(
            environment=required("PROCUREMENT_ENVIRONMENT"),
            service_name=values.get(
                "PROCUREMENT_SERVICE_NAME", "procurement-workflow-assistant"
            ).strip(),
            backend_base_url=(
                required("PROCUREMENT_BACKEND_BASE_URL")
                if backend_mode is BackendMode.HTTP
                else values.get("PROCUREMENT_BACKEND_BASE_URL", "http://unused.invalid").strip()
            ),
            backend_request_timeout_seconds=float(
                values.get("PROCUREMENT_BACKEND_REQUEST_TIMEOUT_SECONDS", "10")
            ),
            identity_gateway_secret=SecretStr(
                required("PROCUREMENT_IDENTITY_GATEWAY_SECRET")
                if backend_mode is BackendMode.HTTP
                else values.get(
                    "PROCUREMENT_IDENTITY_GATEWAY_SECRET", "unused-in-fake-mode"
                ).strip()
            ),
            backend_mode=backend_mode,
            fake_data_path=values.get(
                "PROCUREMENT_FAKE_DATA_PATH", ".local/fake-users.json"
            ).strip(),
            llm_enabled=_parse_bool(values.get("PROCUREMENT_LLM_ENABLED", "false")),
            llm_base_url=llm_base_url or None,
            llm_api_key=SecretStr(llm_api_key) if llm_api_key else None,
            llm_model=llm_model or None,
            llm_timeout_seconds=float(values.get("PROCUREMENT_LLM_TIMEOUT_SECONDS", "30")),
            llm_max_tool_steps=int(values.get("PROCUREMENT_LLM_MAX_TOOL_STEPS", "6")),
            llm_max_total_tool_calls=int(values.get("PROCUREMENT_LLM_MAX_TOTAL_TOOL_CALLS", "24")),
            llm_max_history_messages=int(values.get("PROCUREMENT_LLM_MAX_HISTORY_MESSAGES", "20")),
            llm_max_tool_result_chars=int(
                values.get("PROCUREMENT_LLM_MAX_TOOL_RESULT_CHARS", "20000")
            ),
            llm_context_knowledge_path=(
                values.get("LLM_CONTEXT_KNOWLEDGE_PATH", "").strip() or None
            ),
            llm_role_skills_path=(
                values.get("PROCUREMENT_LLM_ROLE_SKILLS_PATH", "skills").strip() or None
            ),
            llm_skill_routing_mode=values.get("PROCUREMENT_LLM_SKILL_ROUTING_MODE", "strict")
            .strip()
            .lower(),
            allow_test_platform=_parse_bool(values.get("PROCUREMENT_ALLOW_TEST_PLATFORM", "false")),
            event_dedup_store_backend=values.get(
                "PROCUREMENT_EVENT_DEDUP_STORE_BACKEND", "memory"
            ).strip(),
            conversation_lock_backend=values.get(
                "PROCUREMENT_CONVERSATION_LOCK_BACKEND", "local"
            ).strip(),
            redis_url=(
                SecretStr(values["PROCUREMENT_REDIS_URL"].strip())
                if values.get("PROCUREMENT_REDIS_URL", "").strip()
                else None
            ),
            redis_timeout_seconds=float(values.get("PROCUREMENT_REDIS_TIMEOUT_SECONDS", "2")),
            event_dedup_ttl_seconds=int(
                values.get("PROCUREMENT_FEISHU_EVENT_DEDUP_TTL_SECONDS", "86400")
            ),
            conversation_lock_ttl_seconds=int(
                values.get("PROCUREMENT_CONVERSATION_LOCK_TTL_SECONDS", "60")
            ),
            conversation_lock_acquire_timeout_seconds=float(
                values.get("PROCUREMENT_CONVERSATION_LOCK_ACQUIRE_TIMEOUT_SECONDS", "5")
            ),
            notification_delivery_ttl_seconds=int(
                values.get("PROCUREMENT_NOTIFICATION_DELIVERY_TTL_SECONDS", "604800")
            ),
            fault_knowledge_path=values.get(
                "FAULT_KNOWLEDGE_PATH", "knowledge/fault-guidance"
            ).strip(),
            fault_state_ttl_seconds=int(values.get("FAULT_STATE_TTL_SECONDS", "86400")),
            fault_guidance_enabled=_parse_bool(
                values.get("PROCUREMENT_FAULT_GUIDANCE_ENABLED", "false")
            ),
            debug_identity_probe_enabled=_parse_bool(
                values.get("PROCUREMENT_DEBUG_IDENTITY_PROBE_ENABLED", "false")
            ),
            development_notification_renderer_enabled=_parse_bool(
                values.get("PROCUREMENT_DEVELOPMENT_NOTIFICATION_RENDERER_ENABLED", "false")
            ),
            log_level=values.get("PROCUREMENT_LOG_LEVEL", "INFO").strip().upper(),
            log_format=values.get("PROCUREMENT_LOG_FORMAT", "text").strip().lower(),
            feishu=FeishuSettings(
                enabled=_parse_bool(values.get("PROCUREMENT_FEISHU_ENABLED", "false")),
                app_id=values.get("PROCUREMENT_FEISHU_APP_ID", "").strip(),
                app_secret=SecretStr(values.get("PROCUREMENT_FEISHU_APP_SECRET", "").strip()),
                verification_token=SecretStr(
                    values.get("PROCUREMENT_FEISHU_VERIFICATION_TOKEN", "").strip()
                ),
                encrypt_key=SecretStr(encrypt_key) if encrypt_key else None,
                webhook_path=values.get(
                    "PROCUREMENT_FEISHU_WEBHOOK_PATH", "/webhooks/feishu"
                ).strip(),
            ),
            notification_gateway=NotificationGatewaySettings(
                enabled=_parse_bool(
                    values.get("PROCUREMENT_NOTIFICATION_GATEWAY_ENABLED", "false")
                ),
                path=values.get(
                    "PROCUREMENT_NOTIFICATION_GATEWAY_PATH", "/internal/notifications"
                ).strip(),
                bearer_token=SecretStr(gateway_token) if gateway_token else None,
                delivery_store_backend=values.get(
                    "PROCUREMENT_NOTIFICATION_DELIVERY_STORE_BACKEND", "memory"
                ).strip(),
            ),
        )
