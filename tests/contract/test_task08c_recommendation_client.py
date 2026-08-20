import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from procurement_platform.domain.requirement import SelectedProduct
from tests.contract.test_http_backend_client import envelope, identity, make_client

NOW = datetime(2026, 8, 1, tzinfo=UTC).isoformat()


def context() -> dict[str, object]:
    return {
        "request_id": 9,
        "request_item_id": 101,
        "item_name": "UPS蓄电池",
        "equipment_category_id": 7,
        "equipment_model_id": None,
        "brand": None,
        "model": None,
        "quantity": "32",
        "unit": "块",
    }


def product_response() -> dict[str, object]:
    return {
        "request_item_id": 101,
        "query_context": context(),
        "status": "OK",
        "candidate_count": 1,
        "returned_count": 1,
        "policy_version": "product-v1",
        "warnings": [{"code": "COMPATIBILITY_NOT_VERIFIED", "message": "未验证兼容性"}],
        "recommendations": [
            {
                "rank": 1,
                "product_key": "model:123",
                "equipment_model_id": 123,
                "item_name": "UPS蓄电池",
                "brand": "Panasonic",
                "model": "LC-P12100",
                "candidate_type": "EQUIPMENT_MODEL",
                "match_level": "STRICT",
                "overall_score": "92.50",
                "historical_purchase_count": 12,
                "last_purchased_at": NOW,
                "active_supplier_count": 3,
                "price_summary": None,
                "score_breakdown": {
                    "relevance_score": "100",
                    "frequency_score": "80",
                    "recency_score": "70",
                    "supplier_coverage_score": "60",
                    "relevance_weight": "0.50",
                    "frequency_weight": "0.20",
                    "recency_weight": "0.15",
                    "supplier_coverage_weight": "0.15",
                },
                "reasons": [{"code": "STRICT_MODEL_MATCH", "message": "型号严格匹配"}],
                "warnings": [{"code": "LOW_SAMPLE_SIZE", "message": "样本较少"}],
            }
        ],
    }


def supplier_response(selected: dict[str, object]) -> dict[str, object]:
    return {
        "request_item_id": 101,
        "query_context": context(),
        "selected_product": selected,
        "candidate_count": 2,
        "eligible_candidate_count": 1,
        "returned_count": 1,
        "policy_version": "supplier-v1",
        "recommendations": [
            {
                "rank": 1,
                "supplier_id": 60,
                "supplier_name": "供应商A",
                "overall_score": "88.4",
                "match_level": "STRICT",
                "history_purchase_count": 7,
                "last_purchase_at": NOW,
                "price_summary": {
                    "median_unit_price": "2180",
                    "min_unit_price": "2100",
                    "max_unit_price": "2250",
                    "latest_unit_price": "2200",
                    "sample_count": 7,
                    "currency": "CNY",
                },
                "delivery_summary": {"median_delivery_days": "6", "sample_count": 6},
                "confidence_summary": {"evidence_count": 7, "confidence_score": "0.9"},
                "score_breakdown": {
                    "relevance_score": "100",
                    "price_score": "70",
                    "delivery_score": "80",
                    "confidence_score": "90",
                    "relevance_weight": "0.4",
                    "price_weight": "0.25",
                    "delivery_weight": "0.2",
                    "confidence_weight": "0.15",
                    "effective_weight_sum": "1",
                },
                "reasons": [{"code": "STRICT_HISTORY", "message": "严格历史证据"}],
                "warnings": [{"code": "STALE_HISTORY", "message": "历史较旧"}],
            }
        ],
        "excluded_candidates": [
            {
                "supplier_id": 61,
                "supplier_name": "供应商B",
                "match_level": "STRICT",
                "exclusion_code": "ACTIVE_BLACKLIST",
                "exclusion_reason": "黑名单",
            }
        ],
        "warnings": [{"code": "NO_DELIVERY_DATA", "message": "部分候选缺交期"}],
    }


@pytest.mark.asyncio
async def test_item_recommendation_transport_preserves_backend_evidence() -> None:
    requests: list[httpx.Request] = []
    selected = SelectedProduct(
        product_key="model:123",
        equipment_model_id=123,
        equipment_category_id=7,
        item_name="UPS蓄电池",
        brand="Panasonic",
        model="LC-P12100",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        data = (
            product_response()
            if request.method == "GET"
            else supplier_response(selected.model_dump(mode="json"))
        )
        return httpx.Response(200, json=envelope(data))

    client, raw = make_client(handler)
    products = await client.recommend_products(identity=identity(), request_item_id=101, top_k=10)
    suppliers = await client.recommend_suppliers(
        identity=identity(), request_item_id=101, selected_product=selected, top_k=5
    )
    assert requests[0].url.path == "/api/v1/recommendations/items/101/products"
    assert requests[0].url.params["top_k"] == "10"
    assert requests[1].method == "POST"
    assert json.loads(requests[1].content) == {
        "selected_product": selected.model_dump(mode="json"),
        "top_k": 5,
    }
    assert products.recommendations[0].overall_score == Decimal("92.50")
    assert products.warnings[0].code == "COMPATIBILITY_NOT_VERIFIED"
    assert suppliers.recommendations[0].reasons[0].code == "STRICT_HISTORY"
    assert suppliers.excluded_candidates[0].exclusion_code == "ACTIVE_BLACKLIST"
    assert suppliers.warnings[0].code == "NO_DELIVERY_DATA"
    await raw.aclose()
