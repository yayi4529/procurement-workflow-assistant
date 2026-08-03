import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.requirement import PurchaseFieldsPatch, SupplierUpsertCommand
from tests.contract.test_http_backend_client import envelope, identity, make_client


@pytest.mark.asyncio
async def test_purchaser_endpoint_contracts() -> None:
    requests: list[httpx.Request] = []
    transition = {
        "requirement_id": 1,
        "requirement_no": "PR-1",
        "status": "PURCHASING",
        "version": 5,
        "current_handler": {"employee_id": 9, "name": "采购员"},
        "action_token": None,
    }
    supplier = {
        "supplier_id": 8,
        "supplier_name": "示例供应商",
        "unified_social_credit_code": "TAX-8",
        "blacklist_status": "NONE",
    }
    _purchase = {
        "supplier_id": 8,
        "supplier_tax_number": "TAX-8",
        "bank_name": "示例银行",
        "bank_account": "****5678",
        "registered_address": "示例地址",
        "contract_contact_info": "contact@example.com",
        "actual_unit_price": "12.50",
        "actual_total_price": "25.00",
        "tax_rate": "13",
        "purchased_at": "2026-07-30T10:00:00Z",
        "purchase_remark": None,
        "update_supplier_profile": False,
    }
    responses: list[object] = [
        transition,
        {"items": [supplier], "page": 1, "page_size": 20, "total": 1},
        {
            "supplier_id": 8,
            "supplier_name": supplier["supplier_name"],
            "unified_social_credit_code": "TAX-8",
            "bank_name": "示例银行",
            "bank_account": "****5678",
            "registered_address": "示例地址",
            "contract_contact_info": "contact@example.com",
            "blacklist": {"status": "NONE", "history_count": 0},
        },
        {"supplier_id": 9, "supplier_name": "新供应商"},
        {
            "requirement_id": 1,
            "status": "PURCHASING",
            "version": 6,
            "missing_fields": [],
            "next_missing_field": None,
            "fields_complete": True,
        },
        {
            "items": [{"employee_id": 12, "name": "仓库管理员", "mobile": None}],
            "auto_selected_employee_id": 12,
        },
        {
            **transition,
            "status": "PENDING_WAREHOUSE",
            "version": 7,
            "current_handler": {"employee_id": 12, "name": "仓库管理员"},
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=envelope(responses[len(requests) - 1]))

    client, raw = make_client(handler)
    token = UUID("00000000-0000-0000-0000-000000000001")
    await client.start_purchase(
        identity=identity(), requirement_id=1, expected_version=4, action_token=token
    )
    await client.search_suppliers(identity=identity(), keyword="示例")
    await client.get_supplier(identity=identity(), supplier_id=8)
    await client.create_supplier(
        identity=identity(),
        command=SupplierUpsertCommand(supplier_name="新供应商", bank_account="6222000012345678"),
    )
    await client.update_purchase_fields(
        identity=identity(),
        requirement_id=1,
        expected_version=5,
        fields=PurchaseFieldsPatch(
            actual_unit_price="12.50",
            tax_rate="13",
            purchased_at=datetime(2026, 7, 30, 10, tzinfo=UTC),
        ),
    )
    await client.list_handler_candidates(
        identity=identity(), requirement_id=1, target_role=RoleCode.WAREHOUSE_MANAGER
    )
    await client.submit_warehouse(
        identity=identity(),
        requirement_id=1,
        expected_version=6,
        assigned_to_employee_id=12,
        action_token=token,
    )
    assert [(x.method, x.url.path) for x in requests] == [
        ("POST", "/api/v1/requirements/1/start-purchase"),
        ("GET", "/api/v1/suppliers"),
        ("GET", "/api/v1/suppliers/8"),
        ("POST", "/api/v1/suppliers"),
        ("PATCH", "/api/v1/requirements/1/purchase-fields"),
        ("GET", "/api/v1/requirements/1/handler-candidates"),
        ("POST", "/api/v1/requirements/1/submit-warehouse"),
    ]
    assert requests[1].url.params["keyword"] == "示例"
    assert requests[5].url.params["target_role"] == "WAREHOUSE_MANAGER"
    assert json.loads(requests[4].content)["fields"]["actual_unit_price"] == "12.50"
    assert "supplier_id" not in json.loads(requests[4].content)["fields"]
    assert "actual_total_price" not in json.loads(requests[4].content)["fields"]
    create_supplier = json.loads(requests[3].content)
    assert "supplier_tax_number" not in create_supplier
    assert create_supplier["unified_social_credit_code"] is None
    assert "operator_employee_id" not in json.loads(requests[6].content)
    await raw.aclose()
