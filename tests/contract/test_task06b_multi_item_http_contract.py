import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from procurement_platform.adapters.backend.dto import BackendReviewItemDTO
from procurement_platform.domain.enums import PurchaseItemKind, RequestType
from procurement_platform.domain.requirement import PurchaseFieldsPatch, RequestItemDraft
from tests.contract.test_http_backend_client import envelope, identity, make_client


def test_review_item_detail_contract_preserves_fields_needed_for_safe_item_edit() -> None:
    item = BackendReviewItemDTO.model_validate(
        {
            "review_item_id": 801,
            "request_item_id": 81,
            "item_kind_snapshot": "COMPONENT",
            "item_name_snapshot": "UPS蓄电池",
            "quantity_snapshot": "32",
            "unit_snapshot": "块",
            "brand_snapshot": "Panasonic",
            "model_snapshot": "LC-P12100",
            "proposed_supplier_id": 60,
            "proposed_supplier_name": "供应商A",
            "supplier_contact_name": "王工",
            "supplier_contact_info": "13800000000",
            "supplier_link": "https://supplier.example/a",
            "estimated_unit_price": "100.00",
            "estimated_total_price": "3200.00",
            "need_contract": True,
            "contract_type": "采购合同",
            "payment_method": "对公转账",
            "expected_arrival_date": "2026-08-30",
            "warranty_info": "一年",
            "item_remark": "优先交付",
        }
    )
    assert item.supplier_contact_name == "王工"
    assert item.need_contract is True
    assert item.warranty_info == "一年"


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
