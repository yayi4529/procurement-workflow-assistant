import json

import httpx
import pytest

from tests.contract.test_http_backend_client import NOW, envelope, identity, make_client


@pytest.mark.asyncio
async def test_task9_read_endpoint_contracts_and_explicit_mapping() -> None:
    requests: list[httpx.Request] = []
    responses: list[object] = [
        {
            "items": [
                {
                    "requirement_id": 1,
                    "requirement_no": "PR-1",
                    "device_name": "服务器",
                    "brand": "戴尔",
                    "model": "R750",
                    "quantity": "2",
                    "unit": "台",
                    "status": "PURCHASING",
                    "supplier_id": 10,
                    "supplier_name": "供应商A",
                    "actual_total_price": "200.00",
                    "purchased_at": NOW,
                    "created_at": NOW,
                    "submitted_at": NOW,
                    "reviewed_at": NOW,
                    "received_at": None,
                    "completed_at": None,
                }
            ],
            "page": 1,
            "page_size": 20,
            "total": 1,
        },
        {
            "items": [
                {
                    "log_id": 3,
                    "action_type": "SUBMIT_PURCHASER",
                    "operator_name": "楼长",
                    "operator_role_name": "楼长",
                    "operator_mobile_masked": None,
                    "from_status": "PENDING_REVIEW",
                    "to_status": "PENDING_PURCHASE",
                    "assigned_to_employee_id": 9,
                    "assigned_to_name": "采购员",
                    "assigned_to_mobile_masked": None,
                    "operation_summary": "提交采购员",
                    "operated_at": NOW,
                }
            ]
        },
        {
            "items": [
                {
                    "brand": "戴尔",
                    "model": "R750",
                    "historical_count": 2,
                    "last_purchased_at": NOW,
                }
            ]
        },
        {
            "items": [
                {
                    "requirement_id": 2,
                    "device_name": "服务器",
                    "brand": "戴尔",
                    "model": "R750",
                    "quantity": "1",
                    "supplier_id": 10,
                    "supplier_name": "供应商A",
                    "actual_total_price": "100",
                    "purchased_at": NOW,
                    "blacklist_status": "INACTIVE",
                }
            ]
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=envelope(responses[len(requests) - 1]))

    client, raw_client = make_client(handler)
    records = await client.list_purchase_records(
        identity=identity(),
        device_name="服务器",
        brand="戴尔",
        page=1,
        page_size=20,
    )
    timeline = await client.get_requirement_timeline(identity=identity(), requirement_id=1)
    products = await client.recommend_products(identity=identity(), device_name="服务器", limit=3)
    history = await client.recommend_purchase_history(
        identity=identity(), requirement_id=1, limit=10
    )

    assert records.items[0].quantity == "2"
    assert timeline.items[0].to_status.value == "PENDING_PURCHASE"
    assert products.items[0].historical_count == 2
    assert history.items[0].actual_total_price == "100"
    assert [request.url.path for request in requests] == [
        "/api/v1/purchase-records",
        "/api/v1/requirements/1/timeline",
        "/api/v1/recommendations/products",
        "/api/v1/recommendations/purchase-history",
    ]
    assert requests[0].url.params["device_name"] == "服务器"
    assert requests[2].url.params["limit"] == "3"
    assert requests[3].url.params["requirement_id"] == "1"
    assert json.loads(requests[0].headers["x-gateway-timestamp"]) > 0
    await raw_client.aclose()
