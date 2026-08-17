from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from procurement_platform.adapters.backend.http_client import HttpBackendClient
from procurement_platform.adapters.backend.signer import GatewayIdentitySigner
from procurement_platform.adapters.backend.transport import SignedBackendTransport
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.identity import PlatformIdentity
from tests.unit.test_signer import FixedClock, SequenceNonce


def envelope(data: object) -> dict[str, object]:
    return {
        "success": True,
        "code": "OK",
        "message": "ok",
        "data": data,
        "trace_id": "trace-assets",
    }


def client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[HttpBackendClient, httpx.AsyncClient]:
    signer = GatewayIdentitySigner(
        SecretStr("secret"),
        clock=FixedClock(),
        nonce_factory=SequenceNonce("0000000000000001", "0000000000000002"),
    )
    raw = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpBackendClient(
        SignedBackendTransport(
            base_url="http://backend", timeout_seconds=2, signer=signer, client=raw
        )
    ), raw


def asset_data() -> dict[str, object]:
    now = datetime(2026, 8, 17, tzinfo=UTC).isoformat()
    return {
        "asset_id": 108,
        "asset_code": "TEST-UPS-A2-01",
        "asset_name": "二层2号UPS",
        "category_id": 14,
        "model_id": None,
        "building_id": 1,
        "location": "二层UPS室",
        "serial_number": None,
        "status": "ACTIVE",
        "criticality": "CRITICAL",
        "commissioned_at": None,
        "warranty_end_at": None,
        "configuration": {"installed_module_count": 8},
        "aliases": ["2号UPS"],
        "redundancy_group": None,
        "redundancy_mode": None,
        "remark": None,
        "version": 0,
        "created_at": now,
        "updated_at": now,
        "category": {
            "category_id": 14,
            "parent_category_id": 1,
            "category_code": "UPS",
            "category_name": "UPS",
            "category_level": 2,
            "description": None,
            "sort_order": 1,
            "status": "ACTIVE",
        },
        "model": None,
        "building": {"building_id": 1, "building_name": "一号楼"},
    }


@pytest.mark.asyncio
async def test_asset_context_is_one_signed_http_round_trip_and_strictly_parsed() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=envelope(
                {"asset": asset_data(), "components": [], "relations": [], "redundancy_peers": []}
            ),
        )

    backend, raw = client(handler)
    result = await backend.get_asset_context(
        identity=PlatformIdentity(PlatformType.FEISHU, "ou_test", "request-test"), asset_id=108
    )
    assert len(requests) == 1
    assert requests[0].url.path == "/api/v1/assets/108/context"
    assert requests[0].headers["x-platform-type"] == "FEISHU"
    assert result.asset.model is None
    assert result.asset.aliases == ("2号UPS",)
    await raw.aclose()


@pytest.mark.asyncio
async def test_asset_search_uses_backend_query_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json=envelope({"items": [asset_data()], "page": 1, "page_size": 10, "total": 1})
        )

    backend, raw = client(handler)
    page = await backend.search_assets(
        identity=PlatformIdentity(PlatformType.FEISHU, "ou_test", "request-test"),
        building_id=1,
        category_code="UPS",
        query="2号UPS",
        page_size=10,
    )
    assert page.total == 1
    assert requests[0].url.params["category_code"] == "UPS"
    assert requests[0].url.params["q"] == "2号UPS"
    await raw.aclose()
