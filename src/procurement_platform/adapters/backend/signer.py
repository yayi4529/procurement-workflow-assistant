import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

from pydantic import SecretStr

from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.identity import PlatformIdentity


class Clock(Protocol):
    def unix_seconds(self) -> int: ...


class NonceFactory(Protocol):
    def create(self) -> str: ...


class SystemClock:
    def unix_seconds(self) -> int:
        return int(time.time())


class SecureNonceFactory:
    def create(self) -> str:
        return secrets.token_hex(16)


@dataclass(frozen=True, slots=True)
class GatewayIdentitySigner:
    secret: SecretStr = field(repr=False)
    allow_test_platform: bool = False
    clock: Clock = field(default_factory=SystemClock)
    nonce_factory: NonceFactory = field(default_factory=SecureNonceFactory)

    def __post_init__(self) -> None:
        if not self.secret.get_secret_value():
            raise ValueError("identity gateway secret must not be empty")

    def sign(self, method: str, url_path: str, identity: PlatformIdentity) -> dict[str, str]:
        if identity.platform_type is PlatformType.TEST_PLATFORM and not self.allow_test_platform:
            raise ValueError("TEST_PLATFORM is disabled")
        path = urlsplit(url_path).path
        if not path.startswith("/"):
            raise ValueError("url_path must be an absolute path")
        nonce = self.nonce_factory.create()
        if not 16 <= len(nonce) <= 128:
            raise ValueError("nonce length must be between 16 and 128")
        timestamp = self.clock.unix_seconds()
        canonical = "\n".join(
            (
                method.upper(),
                path,
                identity.platform_type.value,
                identity.platform_user_id,
                str(timestamp),
                nonce,
            )
        )
        signature = hmac.new(
            self.secret.get_secret_value().encode(),
            canonical.encode(),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-Platform-Type": identity.platform_type.value,
            "X-Platform-User-Id": identity.platform_user_id,
            "X-Gateway-Timestamp": str(timestamp),
            "X-Gateway-Nonce": nonce,
            "X-Gateway-Signature": signature,
            "X-Request-Id": identity.request_id,
        }
