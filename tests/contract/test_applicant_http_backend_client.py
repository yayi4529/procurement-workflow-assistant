import json
from uuid import UUID

import httpx
import pytest

from procurement_platform.domain.enums import RequirementView, RoleCode
from procurement_platform.domain.requirement import ApplicantFieldsPatch
from tests.contract.test_http_backend_client import envelope, identity, make_client


@pytest.mark.asyncio
async def test_applicant_endpoint_contracts_and_string_quantity() -> None:
    requests: list[httpx.Request] = []
    responses: list[object] = [
        {"requirement_id": 1, "requirement_no": "PR-1", "status": "DRAFT", "version": 1},
        {
            "requirement_id": 1,
            "status": "DRAFT",
            "version": 2,
            "missing_fields": [],
            "next_missing_field": None,
            "fields_complete": True,
        },
        {
            "requirement_id": 1,
            "requirement_no": "PR-1",
            "status": "DRAFT",
            "version": 2,
            "building": {"building_id": 1, "building_name": "一号楼"},
            "current_handler": None,
            "applicant_fields": {
                "device_profession": "网络",
                "device_name": "交换机",
                "brand": None,
                "model": None,
                "quantity": "2",
                "unit": "台",
                "application_reason": "扩容",
                "applicant_remark": None,
            },
            "missing_fields": [],
            "allowed_actions": ["SUBMIT_REVIEW"],
            "fields_complete": True,
            "rejection_reason": None,
        },
        {"items": [], "page": 1, "page_size": 20, "total": 0},
        {
            "items": [{"employee_id": 9, "name": "楼长"}],
            "auto_selected_employee_id": 9,
        },
        {
            "requirement_id": 1,
            "requirement_no": "PR-1",
            "status": "PENDING_REVIEW",
            "version": 3,
            "current_handler": {"employee_id": 9, "name": "楼长"},
            "action_token": None,
        },
        {
            "requirement_id": 1,
            "requirement_no": "PR-1",
            "status": "PENDING_REVIEW",
            "version": 4,
            "current_handler": {"employee_id": 9, "name": "楼长"},
            "action_token": None,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=envelope(responses[len(requests) - 1]))

    client, raw = make_client(handler)
    await client.create_requirement(identity=identity(), building_id=1)
    await client.update_applicant_fields(
        identity=identity(),
        requirement_id=1,
        expected_version=1,
        fields=ApplicantFieldsPatch(quantity="2", brand=None),
    )
    await client.get_requirement(identity=identity(), requirement_id=1)
    await client.list_requirements(identity=identity(), view=RequirementView.CREATED_BY_ME)
    await client.list_handler_candidates(
        identity=identity(), requirement_id=1, target_role=RoleCode.BUILDING_MANAGER
    )
    token = UUID("00000000-0000-0000-0000-000000000001")
    await client.submit_review(
        identity=identity(),
        requirement_id=1,
        expected_version=2,
        assigned_to_employee_id=9,
        action_token=token,
    )
    await client.resubmit_review(
        identity=identity(),
        requirement_id=1,
        expected_version=3,
        assigned_to_employee_id=9,
        action_token=token,
    )
    assert [(item.method, item.url.path) for item in requests] == [
        ("POST", "/api/v1/requirements"),
        ("PATCH", "/api/v1/requirements/1/applicant-fields"),
        ("GET", "/api/v1/requirements/1"),
        ("GET", "/api/v1/requirements"),
        ("GET", "/api/v1/requirements/1/handler-candidates"),
        ("POST", "/api/v1/requirements/1/submit-review"),
        ("POST", "/api/v1/requirements/1/resubmit-review"),
    ]
    patch = json.loads(requests[1].content)
    assert patch == {
        "expected_version": 1,
        "fields": {"quantity": "2", "brand": None},
    }
    assert requests[3].url.params["view"] == "CREATED_BY_ME"
    assert requests[3].url.params["page"] == "1"
    assert requests[3].url.params["page_size"] == "20"
    assert requests[4].url.query == b"target_role=BUILDING_MANAGER"
    submit = json.loads(requests[5].content)
    assert submit["action_token"] == str(token)
    assert "operator_employee_id" not in submit
    assert requests[3].headers["x-gateway-signature"]
    await raw.aclose()
