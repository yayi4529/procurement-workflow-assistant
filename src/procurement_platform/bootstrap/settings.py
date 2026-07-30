import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import SecretStr


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("boolean setting must be true or false")


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    service_name: str
    backend_base_url: str
    backend_request_timeout_seconds: float
    identity_gateway_secret: SecretStr = field(repr=False)
    allow_test_platform: bool = False

    def __post_init__(self) -> None:
        if self.backend_request_timeout_seconds <= 0:
            raise ValueError("backend request timeout must be greater than zero")
        if not self.identity_gateway_secret.get_secret_value():
            raise ValueError("identity gateway secret is required")
        if self.environment.lower() == "production" and self.allow_test_platform:
            raise ValueError("TEST_PLATFORM cannot be enabled in production")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ

        def required(name: str) -> str:
            value = values.get(name, "").strip()
            if not value:
                raise ValueError(f"required setting {name} is missing")
            return value

        return cls(
            environment=required("PROCUREMENT_ENVIRONMENT"),
            service_name=required("PROCUREMENT_SERVICE_NAME"),
            backend_base_url=required("PROCUREMENT_BACKEND_BASE_URL"),
            backend_request_timeout_seconds=float(
                required("PROCUREMENT_BACKEND_REQUEST_TIMEOUT_SECONDS")
            ),
            identity_gateway_secret=SecretStr(required("PROCUREMENT_IDENTITY_GATEWAY_SECRET")),
            allow_test_platform=_parse_bool(values.get("PROCUREMENT_ALLOW_TEST_PLATFORM", "false")),
        )
