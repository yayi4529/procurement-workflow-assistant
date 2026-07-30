import json
from uuid import UUID

import httpx
import pytest

from procurement_platform.domain.enums import RequirementStatus, RequirementView, RoleCode
from procurement_platform.domain.requirement import ReviewFieldsPatch
from tests.contract.test_http_backend_client import envelope, identity, make_client


@pytest.mark.asyncio
async def test_building_manager_endpoint_contracts() -> None:
    requests: list[httpx.Request] = []
    review_fields = {
        "proposed_supplier_id": 8,
        "supplier_contact_name": "王工",
        "supplier_contact_info": "13800000000",
        "supplier_link": None,
        "estimated_unit_price": "12.50",
        "estimated_total_price": "25.00",
        "need_contract": False,
        "contract_type": None,
        "payment_method": "对公转账",
        "expected_arrival_date": "2026-08-01",
        "warranty_info": None,
        "review_remark": None,
    }
    responses: list[object] = [
        {"items": [], "page": 1, "page_size": 20, "total": 0},
        {
            "requirement_id": 1,
            "status": "PENDING_REVIEW",
            "version": 3,
            "review_fields": review_fields,
            "review_record": {"review_status": "DRAFT"},
            "missing_fields": [],
            "fields_complete": True,
        },
        {"items": [{"employee_id": 9, "name": "采购员"}], "auto_selected_employee_id": 9},
        {
            "requirement_id": 1,
            "requirement_no": "PR-1",
            "status": "REJECTED",
            "version": 4,
            "current_handler": None,
            "action_token": None,
        },
        {
            "requirement_id": 1,
            "requirement_no": "PR-1",
            "status": "PENDING_PURCHASE",
            "version": 4,
            "current_handler": {"employee_id": 9, "name": "采购员"},
            "action_token": None,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=envelope(responses[len(requests) - 1]))

    client, raw = make_client(handler)
    await client.list_requirements(
        identity=identity(),
        view=RequirementView.PENDING_FOR_ME,
        status=RequirementStatus.PENDING_REVIEW,
    )
    await client.update_review_fields(
        identity=identity(),
        requirement_id=1,
        expected_version=2,
        fields=ReviewFieldsPatch(
            estimated_unit_price="12.50",
            need_contract=False,
            contract_type=None,
        ),
    )
    await client.list_handler_candidates(
        identity=identity(), requirement_id=1, target_role=RoleCode.PURCHASER
    )
    token = UUID("00000000-0000-0000-0000-000000000001")
    await client.reject_requirement(
        identity=identity(),
        requirement_id=1,
        expected_version=3,
        reason="预算不合理",
        action_token=token,
    )
    await client.submit_purchaser(
        identity=identity(),
        requirement_id=1,
        expected_version=3,
        assigned_to_employee_id=9,
        action_token=token,
    )
    assert [(item.method, item.url.path) for item in requests] == [
        ("GET", "/api/v1/requirements"),
        ("PATCH", "/api/v1/requirements/1/review-fields"),
        ("GET", "/api/v1/requirements/1/handler-candidates"),
        ("POST", "/api/v1/requirements/1/reject"),
        ("POST", "/api/v1/requirements/1/submit-purchaser"),
    ]
    patch = json.loads(requests[1].content)
    assert patch == {
        "expected_version": 2,
        "fields": {
            "estimated_unit_price": "12.50",
            "need_contract": False,
            "contract_type": None,
        },
    }
    assert "estimated_total_price" not in patch["fields"]
    assert requests[0].url.params["view"] == "PENDING_FOR_ME"
    assert requests[2].url.query == b"target_role=PURCHASER"
    assert "operator_employee_id" not in json.loads(requests[4].content)
    await raw.aclose()
