import hashlib
import hmac
from dataclasses import dataclass

import pytest
from pydantic import SecretStr

from procurement_platform.adapters.backend.signer import GatewayIdentitySigner
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.identity import PlatformIdentity


@dataclass
class FixedClock:
    value: int = 1_700_000_000

    def unix_seconds(self) -> int:
        return self.value


class SequenceNonce:
    def __init__(self, *values: str) -> None:
        self.values = iter(values)

    def create(self) -> str:
        return next(self.values)


def identity(platform: PlatformType = PlatformType.FEISHU) -> PlatformIdentity:
    return PlatformIdentity(platform, "ou_123", "request-1")


def test_signature_uses_ordered_canonical_path_without_host_or_query() -> None:
    nonce = "0123456789abcdef"
    signer = GatewayIdentitySigner(
        SecretStr("test-secret"),
        allow_test_platform=True,
        clock=FixedClock(),
        nonce_factory=SequenceNonce(nonce),
    )
    headers = signer.sign(
        "get",
        "https://backend.example/api/v1/users/me?expand=roles",
        identity(),
    )
    canonical = "\n".join(("GET", "/api/v1/users/me", "FEISHU", "ou_123", "1700000000", nonce))
    expected = hmac.new(b"test-secret", canonical.encode(), hashlib.sha256).hexdigest()
    assert headers["X-Gateway-Signature"] == expected
    assert headers["X-Gateway-Timestamp"] == "1700000000"
    assert headers["X-Request-Id"] == "request-1"


@pytest.mark.parametrize("nonce", ["short", "x" * 129])
def test_invalid_nonce_lengths_are_rejected(nonce: str) -> None:
    signer = GatewayIdentitySigner(
        SecretStr("secret"),
        clock=FixedClock(),
        nonce_factory=SequenceNonce(nonce),
    )
    with pytest.raises(ValueError, match="nonce length"):
        signer.sign("GET", "/api/v1/users/me", identity())


def test_empty_secret_is_rejected_without_leaking_secret() -> None:
    with pytest.raises(ValueError) as exc_info:
        GatewayIdentitySigner(SecretStr(""))
    assert "secret-value" not in str(exc_info.value)

    signer = GatewayIdentitySigner(SecretStr("secret-value"))
    assert "secret-value" not in repr(signer)


def test_each_signature_uses_a_new_nonce() -> None:
    signer = GatewayIdentitySigner(
        SecretStr("secret"),
        clock=FixedClock(),
        nonce_factory=SequenceNonce("a" * 16, "b" * 16),
    )
    first = signer.sign("GET", "/api/v1/users/me", identity())
    second = signer.sign("GET", "/api/v1/users/me", identity())
    assert first["X-Gateway-Nonce"] != second["X-Gateway-Nonce"]


def test_test_platform_is_rejected_when_disabled() -> None:
    signer = GatewayIdentitySigner(SecretStr("secret"))
    with pytest.raises(ValueError, match="TEST_PLATFORM"):
        signer.sign("GET", "/api/v1/users/me", identity(PlatformType.TEST_PLATFORM))
