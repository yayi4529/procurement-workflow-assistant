import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.assistant.capabilities.products.recommend import (
    RecommendProductsArgs,
    RecommendProductsCapability,
)
from procurement_platform.application.assistant.capabilities.suppliers.capabilities import (
    RecommendSuppliersArgs,
    RecommendSuppliersCapability,
)
from procurement_platform.domain.assistant_session import AgentSessionStateUpdate
from procurement_platform.domain.requirement import (
    ItemProductRecommendations,
    ItemSupplierRecommendations,
    SelectedProduct,
)
from tests.contract.test_task08c_recommendation_client import (
    product_response,
    supplier_response,
)
from tests.unit.test_procurement_intelligence import _context, _identity, _user


@pytest.mark.asyncio
async def test_product_selection_flows_to_supplier_and_is_saved_per_item() -> None:
    client = FakeBackendClient(_user())
    conversation = await client.get_or_create_agent_conversation(
        identity=_identity(), current_action="ASSISTANT_CHAT"
    )
    client.item_product_recommendations[101] = ItemProductRecommendations.model_validate(
        product_response()
    )
    selected = product_response()["recommendations"][0]
    assert isinstance(selected, dict)
    selected_dto = {
        "product_key": selected["product_key"],
        "equipment_model_id": selected["equipment_model_id"],
        "equipment_category_id": 7,
        "item_name": selected["item_name"],
        "brand": selected["brand"],
        "model": selected["model"],
    }
    client.item_supplier_recommendations[101] = ItemSupplierRecommendations.model_validate(
        supplier_response(selected_dto)
    )
    context = _context(conversation.conversation_id)

    products = await RecommendProductsCapability(client).execute(
        args=RecommendProductsArgs(request_item_id=101), context=context
    )
    assert products.status == "SUCCESS"
    suppliers = await RecommendSuppliersCapability(client).execute(
        args=RecommendSuppliersArgs(request_item_id=101, product_ref="item-product:101:1"),
        context=context,
    )
    assert suppliers.status == "SUCCESS"
    state = await client.get_agent_state(
        identity=_identity(), conversation_id=conversation.conversation_id
    )
    assert "recommendation:item:101:selected_product" in state.collected_data
    assert client.call_counts["recommend_products"] == 1
    assert client.call_counts["recommend_suppliers"] == 1


@pytest.mark.asyncio
async def test_product_reference_from_another_item_is_rejected_without_backend_call() -> None:
    client = FakeBackendClient(_user())
    conversation = await client.get_or_create_agent_conversation(
        identity=_identity(), current_action="ASSISTANT_CHAT"
    )
    await client.update_agent_state(
        identity=_identity(),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            collected_data={
                "recommendation:product:item-product:101:1": SelectedProduct(
                    product_key="model:123",
                    equipment_model_id=123,
                    equipment_category_id=7,
                    item_name="UPS蓄电池",
                    brand="Panasonic",
                    model="LC-P12100",
                ).model_dump_json()
            }
        ),
    )
    result = await RecommendSuppliersCapability(client).execute(
        args=RecommendSuppliersArgs(request_item_id=102, product_ref="item-product:101:1"),
        context=_context(conversation.conversation_id),
    )
    assert result.status == "INVALID_ARGUMENTS"
    assert client.call_counts["recommend_suppliers"] == 0
