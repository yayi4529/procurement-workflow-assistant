import json

import httpx
import pytest

from tests.contract.test_http_backend_client import envelope, identity, make_client

CATALOG = {
    "version": "1.0",
    "dialect": "mysql",
    "synthetic_default_included": True,
    "views": [],
    "metrics": [],
}
QUERY_SQL = (
    "SELECT item_name, COUNT(*) purchase_count FROM analytics_purchase_item_fact GROUP BY item_name"
)


@pytest.mark.asyncio
async def test_analytics_http_contract_uses_signed_backend_transport() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=envelope(CATALOG))
        return httpx.Response(
            200,
            json=envelope(
                {
                    "query_id": "q-1",
                    "columns": ["item_name", "purchase_count"],
                    "rows": [{"item_name": "控制电源", "purchase_count": 8}],
                    "row_count": 1,
                    "truncated": False,
                    "duration_ms": 12,
                    "normalized_sql": QUERY_SQL,
                    "synthetic_included": True,
                }
            ),
        )

    client, raw = make_client(handler)
    catalog = await client.get_analytics_catalog(identity=identity())
    result = await client.run_analytics_query(
        identity=identity(),
        question="各物品采购次数",
        sql=QUERY_SQL,
        include_synthetic=True,
    )

    assert catalog.version == "1.0"
    assert result.rows[0]["purchase_count"] == 8
    assert [request.url.path for request in requests] == [
        "/api/v1/analytics/catalog",
        "/api/v1/analytics/query",
    ]
    body = json.loads(requests[1].content)
    assert body["include_synthetic"] is True
    assert requests[1].headers["X-Gateway-Signature"]
    await raw.aclose()
