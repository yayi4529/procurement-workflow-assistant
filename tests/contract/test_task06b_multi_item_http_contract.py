import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from procurement_platform.domain.enums import PurchaseItemKind, RequestType
from procurement_platform.domain.requirement import PurchaseFieldsPatch, RequestItemDraft
from tests.contract.test_http_backend_client import envelope, identity, make_client


@pytest.mark.asyncio
async def test_multi_item_write_contract_preserves_metadata_and_action_tokens() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        data = {
            "requirement_id": 8,
            "status": "PURCHASING",
            "version": len(requests) + 1,
            "missing_fields": [],
            "next_missing_field": None,
            "fields_complete": True,
        }
        if request.url.path.endswith("submit-warehouse"):
            data = {
                "requirement_id": 8,
                "requirement_no": "PR-8",
                "status": "COMPLETED",
                "version": len(requests) + 1,
                "current_handler": None,
                "completed_at": datetime(2026, 8, 18, tzinfo=UTC).isoformat(),
            }
        return httpx.Response(200, json=envelope(data))

    client, raw = make_client(handler)
    await client.replace_request_items(
        identity=identity(),
        requirement_id=8,
        expected_version=1,
        request_type=RequestType.MAINTENANCE,
        source_asset_id=970001,
        items=(
            RequestItemDraft(
                item_kind=PurchaseItemKind.COMPONENT,
                item_name="蓄电池",
                quantity="3",
                unit="块",
            ),
            RequestItemDraft(
                item_kind=PurchaseItemKind.SERVICE,
                item_name="检测服务",
                quantity="1",
                unit="次",
                requires_warehouse=False,
            ),
        ),
    )
    token = UUID("00000000-0000-0000-0000-000000000006")
    await client.update_purchase_item(
        identity=identity(),
        requirement_id=8,
        request_item_id=81,
        expected_version=2,
        action_token=token,
        fields=PurchaseFieldsPatch(
            supplier_id=3,
            actual_unit_price="100.00",
            purchased_at=datetime(2026, 8, 18, tzinfo=UTC),
        ),
    )
    await client.submit_warehouse(
        identity=identity(),
        requirement_id=8,
        expected_version=3,
        assigned_to_employee_id=None,
        action_token=token,
    )

    replace_body = json.loads(requests[0].content)
    assert replace_body["request_type"] == "MAINTENANCE"
    assert replace_body["source_asset_id"] == 970001
    assert len(replace_body["items"]) == 2
    purchase_body = json.loads(requests[1].content)
    assert purchase_body["action_token"] == str(token)
    assert purchase_body["fields"]["supplier_id"] == 3
    finish_body = json.loads(requests[2].content)
    assert finish_body["assigned_to_employee_id"] is None
    assert finish_body["action_token"] == str(token)
    await raw.aclose()
