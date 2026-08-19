import time
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.gateway_auth import build_gateway_signature
from app.db.session import async_session_factory, engine
from app.main import app
from app.models.procurement import PurchaseRequest, PurchaseRequestItem
from app.services.recommendation.service import RecommendationCoreService
from app.services.recommendation.types import SelectedProductRef


def signed_headers(method: str, path: str, platform_user_id: str) -> dict[str, str]:
    settings = get_settings()
    timestamp = str(int(time.time()))
    nonce = uuid4().hex
    platform_type = "TEST_PLATFORM"
    return {
        "X-Platform-Type": platform_type,
        "X-Platform-User-Id": platform_user_id,
        "X-Gateway-Timestamp": timestamp,
        "X-Gateway-Nonce": nonce,
        "X-Gateway-Signature": build_gateway_signature(
            secret=settings.identity_gateway_secret,
            method=method,
            path=path,
            platform_type=platform_type,
            platform_user_id=platform_user_id,
            timestamp=timestamp,
            nonce=nonce,
        ),
    }


async def call(
    client: AsyncClient,
    method: str,
    path: str,
    platform_user_id: str,
    **kwargs,
):
    return await client.request(
        method,
        path,
        headers=signed_headers(method, path, platform_user_id),
        **kwargs,
    )


async def synthetic_item(*, generic: bool) -> PurchaseRequestItem:
    async with async_session_factory() as session:
        statement = (
            select(PurchaseRequestItem)
            .join(PurchaseRequest, PurchaseRequest.request_id == PurchaseRequestItem.request_id)
            .where(PurchaseRequest.request_no.like("TEST-T08SYN-%"))
        )
        if generic:
            statement = statement.where(
                PurchaseRequestItem.equipment_model_id.is_(None),
                PurchaseRequestItem.brand_snapshot.is_(None),
            )
        else:
            statement = statement.where(PurchaseRequestItem.equipment_model_id.is_not(None))
        item = await session.scalar(
            statement.order_by(PurchaseRequestItem.request_item_id).limit(1)
        )
        assert item is not None, "Task08 synthetic history must be seeded before API tests"
        return item


@pytest.fixture(autouse=True)
async def dispose_engine() -> None:
    await engine.dispose()
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_product_api_top_k_contract_and_stability() -> None:
    item = await synthetic_item(generic=True)
    path = f"/api/v1/recommendations/items/{item.request_item_id}/products"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await call(client, "GET", path, "test-user-01", params={"top_k": 3})
        second = await call(client, "GET", path, "test-user-01", params={"top_k": 3})
    assert first.status_code == 200, first.text
    assert first.json()["data"] == second.json()["data"]
    data = first.json()["data"]
    assert data["status"] == "OK"
    assert data["returned_count"] <= 3
    assert data["policy_version"] == "task08-v1"
    assert data["query_context"]["request_item_id"] == item.request_item_id
    recommendation = data["recommendations"][0]
    assert recommendation["score_breakdown"]["relevance_weight"] == "0.50"
    assert recommendation["price_summary"] is None
    assert "COMPATIBILITY_NOT_VERIFIED" in {
        warning["code"] for warning in recommendation["warnings"]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("top_k", [0, 11])
async def test_product_api_rejects_invalid_top_k(top_k: int) -> None:
    item = await synthetic_item(generic=True)
    path = f"/api/v1/recommendations/items/{item.request_item_id}/products"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await call(client, "GET", path, "test-user-01", params={"top_k": top_k})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_product_api_returns_not_found_and_already_specified() -> None:
    specified = await synthetic_item(generic=False)
    specified_path = f"/api/v1/recommendations/items/{specified.request_item_id}/products"
    missing_path = "/api/v1/recommendations/items/999999999999/products"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await call(client, "GET", specified_path, "test-user-01")
        missing = await call(client, "GET", missing_path, "test-user-01")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PRODUCT_ALREADY_SPECIFIED"
    assert response.json()["data"]["recommendations"] == []
    assert missing.status_code == 404
    assert missing.json()["code"] == "REQUEST_ITEM_NOT_FOUND"


@pytest.mark.asyncio
async def test_product_api_returns_no_historical_candidates() -> None:
    path = "/api/v1/recommendations/items/98001/products"
    async with async_session_factory() as session:
        await session.execute(
            update(PurchaseRequestItem)
            .where(PurchaseRequestItem.request_item_id == 98001)
            .values(brand_snapshot=None, model_snapshot=None)
        )
        await session.commit()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await call(client, "GET", path, "test-user-01")
    finally:
        async with async_session_factory() as session:
            await session.execute(
                update(PurchaseRequestItem)
                .where(PurchaseRequestItem.request_item_id == 98001)
                .values(brand_snapshot="TEST-BRAND", model_snapshot="TEST-MODEL-91001")
            )
            await session.commit()
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "NO_HISTORICAL_CANDIDATES"
    assert response.json()["data"]["candidate_count"] == 0


@pytest.mark.asyncio
async def test_supplier_api_requires_selected_product_for_generic_item() -> None:
    item = await synthetic_item(generic=True)
    path = f"/api/v1/recommendations/items/{item.request_item_id}/suppliers"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await call(
            client,
            "POST",
            path,
            "test-user-02",
            json={"selected_product": None, "top_k": 5},
        )
    assert response.status_code == 422
    assert response.json()["code"] == "SELECTED_PRODUCT_REQUIRED"


@pytest.mark.asyncio
async def test_supplier_api_maps_core_result_and_exclusions() -> None:
    async with async_session_factory() as session:
        item = await session.scalar(
            select(PurchaseRequestItem)
            .join(PurchaseRequest, PurchaseRequest.request_id == PurchaseRequestItem.request_id)
            .where(
                PurchaseRequest.request_no.like("TEST-T08SYN-%"),
                PurchaseRequestItem.remark.like("%canonical_item=UPS_BATTERY"),
                PurchaseRequestItem.equipment_model_id.is_(None),
                PurchaseRequestItem.brand_snapshot.is_(None),
            )
            .limit(1)
        )
        assert item is not None
    product_path = f"/api/v1/recommendations/items/{item.request_item_id}/products"
    supplier_path = f"/api/v1/recommendations/items/{item.request_item_id}/suppliers"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        products = await call(client, "GET", product_path, "test-user-01")
        selected = products.json()["data"]["recommendations"][0]
        selected_product = {
            "product_key": selected["product_key"],
            "equipment_model_id": selected["equipment_model_id"],
            "equipment_category_id": item.equipment_category_id,
            "item_name": selected["item_name"],
            "brand": selected["brand"],
            "model": selected["model"],
        }
        response = await call(
            client,
            "POST",
            supplier_path,
            "test-user-02",
            json={"selected_product": selected_product, "top_k": 5},
        )
        limited = await call(
            client,
            "POST",
            supplier_path,
            "test-user-02",
            json={"selected_product": selected_product, "top_k": 2},
        )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["returned_count"] == 5
    assert limited.json()["data"]["returned_count"] == 2
    assert {row["exclusion_code"] for row in data["excluded_candidates"]} >= {
        "ACTIVE_BLACKLIST",
        "SUPPLIER_INACTIVE",
    }
    top = data["recommendations"][0]
    assert top["score_breakdown"]["effective_weight_sum"] == "1.0"
    assert top["confidence_summary"]["evidence_count"] >= 1
    assert top["price_summary"]["currency"] == "CNY"
    assert any(
        warning["code"] in {"LOW_SAMPLE_SIZE", "NO_DELIVERY_DATA"}
        for recommendation in data["recommendations"]
        for warning in recommendation["warnings"]
    )

    direct_selected = SelectedProductRef(
        product_key=selected_product["product_key"],
        equipment_category_id=selected_product["equipment_category_id"],
        equipment_model_id=selected_product["equipment_model_id"],
        item_name=selected_product["item_name"],
        brand=selected_product["brand"],
        model=selected_product["model"],
    )
    async with async_session_factory() as session:
        direct = await RecommendationCoreService().recommend_suppliers(
            session, item.request_item_id, direct_selected, limit=5
        )
    assert [row["supplier_id"] for row in data["recommendations"]] == [
        row.candidate.supplier_id for row in direct.recommendations
    ]
    assert [row["overall_score"] for row in data["recommendations"]] == [
        str(row.overall_score) for row in direct.recommendations
    ]


@pytest.mark.asyncio
async def test_supplier_api_null_product_uses_specified_item_and_validates_input() -> None:
    item = await synthetic_item(generic=False)
    path = f"/api/v1/recommendations/items/{item.request_item_id}/suppliers"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await call(
            client,
            "POST",
            path,
            "test-user-02",
            json={"selected_product": None, "top_k": 5},
        )
        invalid_top_k = await call(
            client,
            "POST",
            path,
            "test-user-02",
            json={"selected_product": None, "top_k": 6},
        )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["selected_product"]["equipment_model_id"] == (
        item.equipment_model_id
    )
    assert invalid_top_k.status_code == 422


@pytest.mark.asyncio
async def test_supplier_api_rejects_selected_product_category_mismatch() -> None:
    item = await synthetic_item(generic=True)
    path = f"/api/v1/recommendations/items/{item.request_item_id}/suppliers"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await call(
            client,
            "POST",
            path,
            "test-user-02",
            json={
                "selected_product": {
                    "product_key": "model:123",
                    "equipment_model_id": 123,
                    "equipment_category_id": 999999,
                    "item_name": "不匹配产品",
                    "brand": "Synthetic",
                    "model": "M-123",
                },
                "top_k": 5,
            },
        )
    assert response.status_code == 422
    assert response.json()["code"] == "SELECTED_PRODUCT_MISMATCH"


def test_openapi_exposes_item_centric_recommendation_contract() -> None:
    schema = app.openapi()
    product_path = "/api/v1/recommendations/items/{request_item_id}/products"
    supplier_path = "/api/v1/recommendations/items/{request_item_id}/suppliers"
    assert product_path in schema["paths"]
    assert supplier_path in schema["paths"]
    top_k = next(
        parameter
        for parameter in schema["paths"][product_path]["get"]["parameters"]
        if parameter["name"] == "top_k"
    )
    assert top_k["schema"]["minimum"] == 1
    assert top_k["schema"]["maximum"] == 10
    supplier_operation = schema["paths"][supplier_path]["post"]
    assert "requestBody" in supplier_operation
    assert "404" in supplier_operation["responses"]
    assert "422" in supplier_operation["responses"]
