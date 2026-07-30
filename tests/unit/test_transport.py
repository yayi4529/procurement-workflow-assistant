import json

import httpx
import pytest
from pydantic import SecretStr

from procurement_platform.adapters.backend.signer import GatewayIdentitySigner
from procurement_platform.adapters.backend.transport import SignedBackendTransport
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.errors import (
    BackendProtocolError,
    BackendTimeoutError,
    BackendUnavailableError,
)
from procurement_platform.domain.identity import PlatformIdentity
from tests.unit.test_signer import FixedClock, SequenceNonce


def identity() -> PlatformIdentity:
    return PlatformIdentity(PlatformType.FEISHU, "ou_1", "req-1")


def signer(*nonces: str) -> GatewayIdentitySigner:
    return GatewayIdentitySigner(
        SecretStr("secret"),
        clock=FixedClock(),
        nonce_factory=SequenceNonce(*nonces),
    )


@pytest.mark.asyncio
async def test_transport_sends_url_query_json_and_signed_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"success": True, "code": "OK", "message": "ok", "data": {}, "trace_id": "t"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = SignedBackendTransport(
        base_url="http://backend/",
        timeout_seconds=3,
        signer=signer("a" * 16, "b" * 16),
        client=client,
    )
    await transport.request(
        method="post",
        path="/api/v1/example",
        identity=identity(),
        query={"page": 2},
        json_body={"quantity": "2"},
    )
    await transport.request(method="GET", path="/api/v1/example", identity=identity())
    first = requests[0]
    assert str(first.url) == "http://backend/api/v1/example?page=2"
    assert json.loads(first.content) == {"quantity": "2"}
    assert first.headers["x-platform-user-id"] == "ou_1"
    assert first.headers["x-gateway-nonce"] == "a" * 16
    assert requests[1].headers["x-gateway-nonce"] == "b" * 16
    await transport.aclose()
    assert client.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (httpx.ReadTimeout("timeout"), BackendTimeoutError),
        (httpx.ConnectError("dns"), BackendUnavailableError),
    ],
)
async def test_transport_maps_network_errors(
    exception: httpx.RequestError, expected: type[Exception]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = SignedBackendTransport(
        base_url="http://backend",
        timeout_seconds=1,
        signer=signer("a" * 16),
        client=client,
    )
    with pytest.raises(expected):
        await transport.request(method="GET", path="/api/v1/test", identity=identity())
    await client.aclose()


@pytest.mark.asyncio
async def test_transport_rejects_non_json_and_preserves_trace_id() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, text="broken", headers={"X-Trace-Id": "trace-1"})
        )
    )
    transport = SignedBackendTransport(
        base_url="http://backend",
        timeout_seconds=1,
        signer=signer("a" * 16),
        client=client,
    )
    with pytest.raises(BackendProtocolError) as exc_info:
        await transport.request(method="GET", path="/api/v1/test", identity=identity())
    assert exc_info.value.trace_id == "trace-1"
    await client.aclose()
