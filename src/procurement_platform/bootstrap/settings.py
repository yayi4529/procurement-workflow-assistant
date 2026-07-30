import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from pydantic import SecretStr


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
        if self.delivery_store_backend != "memory":
            raise ValueError("unsupported notification delivery store backend")


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    service_name: str
    backend_base_url: str
    backend_request_timeout_seconds: float
    identity_gateway_secret: SecretStr = field(repr=False)
    llm_enabled: bool = False
    allow_test_platform: bool = False
    feishu: FeishuSettings = field(default_factory=FeishuSettings)
    notification_gateway: NotificationGatewaySettings = field(
        default_factory=NotificationGatewaySettings
    )

    def __post_init__(self) -> None:
        if self.backend_request_timeout_seconds <= 0:
            raise ValueError("backend request timeout must be greater than zero")
        if not self.identity_gateway_secret.get_secret_value():
            raise ValueError("identity gateway secret is required")
        if self.environment.lower() == "production" and self.allow_test_platform:
            raise ValueError("TEST_PLATFORM cannot be enabled in production")
        if self.environment.lower() == "production" and self.notification_gateway.enabled:
            token = self.notification_gateway.bearer_token
            if token is None or not token.get_secret_value():
                raise ValueError("notification gateway bearer token is required in production")
            if self.notification_gateway.delivery_store_backend == "memory":
                raise ValueError("memory notification delivery store is forbidden in production")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ

        def required(name: str) -> str:
            value = values.get(name, "").strip()
            if not value:
                raise ValueError(f"required setting {name} is missing")
            return value

        encrypt_key = values.get("PROCUREMENT_FEISHU_ENCRYPT_KEY", "").strip()
        gateway_token = values.get("PROCUREMENT_NOTIFICATION_GATEWAY_TOKEN", "").strip()
        return cls(
            environment=required("PROCUREMENT_ENVIRONMENT"),
            service_name=required("PROCUREMENT_SERVICE_NAME"),
            backend_base_url=required("PROCUREMENT_BACKEND_BASE_URL"),
            backend_request_timeout_seconds=float(
                required("PROCUREMENT_BACKEND_REQUEST_TIMEOUT_SECONDS")
            ),
            identity_gateway_secret=SecretStr(required("PROCUREMENT_IDENTITY_GATEWAY_SECRET")),
            llm_enabled=_parse_bool(values.get("PROCUREMENT_LLM_ENABLED", "false")),
            allow_test_platform=_parse_bool(values.get("PROCUREMENT_ALLOW_TEST_PLATFORM", "false")),
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
