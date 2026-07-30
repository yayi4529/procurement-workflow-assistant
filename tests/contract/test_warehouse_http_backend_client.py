import json
from uuid import UUID

import httpx
import pytest

from procurement_platform.domain.requirement import WarehouseFieldsPatch
from tests.contract.test_http_backend_client import envelope, identity, make_client


@pytest.mark.asyncio
async def test_warehouse_endpoint_contracts() -> None:
    requests: list[httpx.Request] = []
    responses: list[object] = [
        {
            "requirement_id": 1,
            "status": "PENDING_WAREHOUSE",
            "version": 8,
            "warehouse_fields": {
                "warehouse_location": "A-01",
                "received_quantity": "2",
                "receipt_remark": None,
            },
            "missing_fields": [],
            "fields_complete": True,
        },
        {
            "requirement_id": 1,
            "requirement_no": "PR-1",
            "status": "COMPLETED",
            "version": 9,
            "current_handler": None,
            "completed_at": "2026-07-30T12:00:00Z",
            "action_token": None,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=envelope(responses[len(requests) - 1]))

    client, raw = make_client(handler)
    token = UUID("00000000-0000-0000-0000-000000000006")
    await client.update_warehouse_fields(
        identity=identity(),
        requirement_id=1,
        expected_version=7,
        fields=WarehouseFieldsPatch(
            warehouse_location="A-01", received_quantity="2", receipt_remark=None
        ),
    )
    await client.complete_requirement(
        identity=identity(),
        requirement_id=1,
        expected_version=8,
        action_token=token,
    )
    assert [(request.method, request.url.path) for request in requests] == [
        ("PATCH", "/api/v1/requirements/1/warehouse-fields"),
        ("POST", "/api/v1/requirements/1/complete"),
    ]
    patch = json.loads(requests[0].content)
    assert patch["expected_version"] == 7
    assert patch["fields"]["received_quantity"] == "2"
    assert patch["fields"]["receipt_remark"] is None
    complete = json.loads(requests[1].content)
    assert complete == {"expected_version": 8, "action_token": str(token)}
    assert "operator_employee_id" not in complete
    await raw.aclose()
