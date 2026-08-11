from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.assistant.agent_tools import UpdateReviewDraftTool
from procurement_platform.application.assistant.agents.building_manager import BuildingManagerAgent
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.supplier_recommendation import (
    RecommendSuppliersForRequirementArgs,
    RecommendSuppliersForRequirementTool,
)
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantTextResponse,
    AssistantToolContext,
)
from procurement_platform.domain.assistant_session import (
    AgentSessionStateUpdate,
    RecommendationReference,
)
from procurement_platform.domain.enums import (
    AllowedRequirementAction,
    PlatformType,
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ApplicantFields,
    PurchaseRecord,
    RequirementBuilding,
    RequirementDetail,
    RequirementHandler,
    ReviewFields,
    SupplierBlacklistSummary,
    SupplierDetail,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def manager() -> CurrentUser:
    return CurrentUser(
        employee_id=7,
        name="楼长",
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=RoleCode.BUILDING_MANAGER),),
        buildings=(UserBuilding(building_id=1, building_name="一号楼"),),
    )


def identity() -> PlatformIdentity:
    return PlatformIdentity(PlatformType.FEISHU, "ou_manager", "request")


def context() -> AssistantToolContext:
    return AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id="ou_manager",
        conversation_id=1,
        external_conversation_id="oc_1",
        external_message_id="om_1",
        current_time=datetime.now(UTC),
        timezone_name="Asia/Shanghai",
        current_user=manager(),
    )


def backend() -> FakeBackendClient:
    client = FakeBackendClient(manager())
    client.seed_requirement(
        RequirementDetail(
            requirement_id=1,
            requirement_no="PR-1",
            status=RequirementStatus.PENDING_REVIEW,
            version=2,
            building=RequirementBuilding(building_id=1, building_name="一号楼"),
            current_handler=RequirementHandler(employee_id=7, name="楼长"),
            applicant_fields=ApplicantFields(
                device_profession="网络",
                device_name="交换机",
                brand="华为",
                quantity="2",
                unit="台",
            ),
            missing_fields=(),
            allowed_actions=(AllowedRequirementAction.UPDATE_REVIEW_FIELDS,),
        )
    )
    client.seed_supplier(
        SupplierDetail(
            supplier_id=11,
            supplier_name="可用供应商",
            blacklist=SupplierBlacklistSummary(active=False),
            contract_contact_info="13800000000",
        )
    )
    client.seed_supplier(
        SupplierDetail(
            supplier_id=12,
            supplier_name="黑名单供应商",
            blacklist=SupplierBlacklistSummary(active=True),
        )
    )
    client.purchase_records.extend(
        [
            PurchaseRecord(
                requirement_id=90,
                requirement_no="PR-90",
                device_name="交换机",
                brand="华为",
                status=RequirementStatus.COMPLETED,
                supplier_id=11,
                supplier_name="可用供应商",
                quantity="2",
                actual_total_price="200.00",
                purchased_at=datetime(2026, 7, 1, tzinfo=UTC),
                created_at=datetime(2026, 6, 1, tzinfo=UTC),
            ),
            PurchaseRecord(
                requirement_id=91,
                requirement_no="PR-91",
                device_name="交换机",
                brand="华为",
                status=RequirementStatus.COMPLETED,
                supplier_id=11,
                supplier_name="可用供应商",
                quantity="4",
                actual_total_price="600.00",
                purchased_at=datetime(2026, 8, 1, tzinfo=UTC),
                created_at=datetime(2026, 7, 1, tzinfo=UTC),
            ),
            PurchaseRecord(
                requirement_id=92,
                requirement_no="PR-92",
                device_name="路由器",
                brand="华为",
                status=RequirementStatus.COMPLETED,
                supplier_id=12,
                supplier_name="黑名单供应商",
                purchased_at=datetime(2026, 8, 2, tzinfo=UTC),
                created_at=datetime(2026, 7, 2, tzinfo=UTC),
            ),
        ]
    )
    return client


@pytest.mark.asyncio
async def test_manager_supplier_recommendation_rechecks_backend_and_saves_references() -> None:
    client = backend()
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(), current_action="ASSISTANT_CHAT"
    )
    result = await RecommendSuppliersForRequirementTool(client).execute(
        args=RecommendSuppliersForRequirementArgs(requirement_id=1),
        context=context().model_copy(update={"conversation_id": conversation.conversation_id}),
    )
    saved = await client.get_agent_state(
        identity=identity(), conversation_id=conversation.conversation_id
    )

    assert result.status == "SUCCESS"
    assert result.requirement_version == 2
    assert result.candidates[0].candidate_ref == "supplier:11"
    assert result.candidates[0].supplier_name == "可用供应商"
    assert result.candidates[0].historical_purchase_count == 2
    assert len(result.candidates) == 1
    assert saved.purchase_request_id == 1
    assert saved.last_recommendations[0].reference_id == "supplier:11"
    assert client.call_counts["get_current_user"] == 1
    assert client.call_counts["get_requirement"] == 3
    assert client.call_counts["list_purchase_records"] == 1
    assert client.call_counts["recommend_suppliers"] == 0
    assert result.candidates[0].supplier_contact_info == "13800000000"
    assert result.candidates[0].historical_unit_prices == (
        "2026-07-01: 100.00",
        "2026-08-01: 150.00",
    )


@pytest.mark.asyncio
async def test_supplier_recommendation_refuses_non_pending_requirement() -> None:
    client = backend()
    detail = client._requirements[1]
    client.seed_requirement(
        detail.model_copy(update={"status": RequirementStatus.PENDING_PURCHASE})
    )

    result = await RecommendSuppliersForRequirementTool(client).execute(
        args=RecommendSuppliersForRequirementArgs(requirement_id=1), context=context()
    )

    assert result.status == "INVALID_STATUS"
    assert client.call_counts["recommend_suppliers"] == 0


@pytest.mark.asyncio
async def test_manager_sequence_selection_uses_saved_supplier_reference() -> None:
    client = backend()
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(), current_action="ASSISTANT_CHAT"
    )
    await client.update_agent_state(
        identity=identity(),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            purchase_request_id=1,
            last_recommendations=(
                RecommendationReference(
                    reference_id="supplier:11",
                    kind="SUPPLIER_RECOMMENDATION",
                    label="可用供应商",
                ),
            ),
        ),
    )
    registry = ToolRegistry()
    registry.register(UpdateReviewDraftTool(client))
    agent = BuildingManagerAgent(
        AssistantSessionService(client), ToolExecutor(registry, max_result_chars=5000), client
    )

    response = await agent.before_run(
        context=context().model_copy(update={"conversation_id": conversation.conversation_id}),
        history=(AssistantMessage(role="user", content="1"),),
        user_text="1",
        external_message_id="om_select_1",
    )

    assert isinstance(response, AssistantTextResponse)
    assert "可用供应商" in response.text
    assert "联系人姓名" in response.text
    assert client._requirements[1].review_fields is not None
    assert client._requirements[1].review_fields.proposed_supplier_id == 11


@pytest.mark.asyncio
async def test_manager_pending_field_answer_is_saved_without_recommending_again() -> None:
    client = backend()
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(), current_action="ASSISTANT_CHAT"
    )
    await client.update_agent_state(
        identity=identity(),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            purchase_request_id=1,
            pending_field="estimated_unit_price",
            missing_fields=("estimated_unit_price",),
        ),
    )
    registry = ToolRegistry()
    registry.register(UpdateReviewDraftTool(client))
    agent = BuildingManagerAgent(
        AssistantSessionService(client), ToolExecutor(registry, max_result_chars=5000), client
    )

    response = await agent.before_run(
        context=context().model_copy(update={"conversation_id": conversation.conversation_id}),
        history=(AssistantMessage(role="user", content="16500"),),
        user_text="16500",
        external_message_id="om_price_1",
    )

    assert isinstance(response, AssistantTextResponse)
    assert client.call_counts["recommend_suppliers"] == 0
    assert client._requirements[1].review_fields is not None
    assert client._requirements[1].review_fields.estimated_unit_price == "16500"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "input_date",
    ("2026年8月28日", "2026-08-28", "2026/8/28", "2026.8.28", "20260828"),
)
async def test_manager_arrival_date_formats_are_normalized_and_saved(input_date: str) -> None:
    client = backend()
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(), current_action="ASSISTANT_CHAT"
    )
    await client.update_agent_state(
        identity=identity(),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            purchase_request_id=1,
            pending_field="expected_arrival_date",
            missing_fields=("expected_arrival_date",),
        ),
    )
    registry = ToolRegistry()
    registry.register(UpdateReviewDraftTool(client))
    agent = BuildingManagerAgent(
        AssistantSessionService(client), ToolExecutor(registry, max_result_chars=5000), client
    )

    response = await agent.before_run(
        context=context().model_copy(update={"conversation_id": conversation.conversation_id}),
        history=(AssistantMessage(role="user", content=input_date),),
        user_text=input_date,
        external_message_id="om_arrival_date_1",
    )

    assert isinstance(response, AssistantTextResponse)
    assert "2026-08-28" in response.text
    assert client._requirements[1].review_fields is not None
    assert client._requirements[1].review_fields.expected_arrival_date.isoformat() == "2026-08-28"
    assert client.call_counts["list_purchase_records"] == 0


@pytest.mark.asyncio
async def test_manager_saved_field_acknowledges_before_asking_next_field() -> None:
    client = backend()
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(), current_action="ASSISTANT_CHAT"
    )
    await client.update_agent_state(
        identity=identity(),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            purchase_request_id=1,
            pending_field="payment_method",
            missing_fields=("payment_method",),
        ),
    )
    registry = ToolRegistry()
    registry.register(UpdateReviewDraftTool(client))
    agent = BuildingManagerAgent(
        AssistantSessionService(client), ToolExecutor(registry, max_result_chars=5000), client
    )

    response = await agent.before_run(
        context=context().model_copy(update={"conversation_id": conversation.conversation_id}),
        history=(AssistantMessage(role="user", content="一次性付清"),),
        user_text="一次性付清",
        external_message_id="om_payment_method_1",
    )

    assert isinstance(response, AssistantTextResponse)
    assert "已为您记录付款方式为**一次性付清**" in response.text
    assert "请提供" in response.text


@pytest.mark.asyncio
async def test_manager_contact_question_reads_current_recommended_supplier() -> None:
    client = backend()
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(), current_action="ASSISTANT_CHAT"
    )
    await client.update_agent_state(
        identity=identity(),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            purchase_request_id=1,
            last_recommendations=(
                RecommendationReference(
                    reference_id="supplier:11",
                    kind="SUPPLIER_RECOMMENDATION",
                    label="可用供应商",
                ),
            ),
        ),
    )
    agent = BuildingManagerAgent(
        AssistantSessionService(client), ToolExecutor(ToolRegistry(), max_result_chars=5000), client
    )

    response = await agent.before_run(
        context=context().model_copy(update={"conversation_id": conversation.conversation_id}),
        history=(AssistantMessage(role="user", content="这个供应商的联系人和联系方式是?"),),
        user_text="这个供应商的联系人和联系方式是?",
        external_message_id="om_contact_1",
    )

    assert isinstance(response, AssistantTextResponse)
    assert "13800000000" in response.text
    assert client.call_counts["get_supplier"] == 1


@pytest.mark.asyncio
async def test_manager_saves_selected_historical_contact_then_asks_next_field() -> None:
    client = backend()
    historical = client._requirements[1].model_copy(
        update={
            "requirement_id": 90,
            "requirement_no": "PR-90",
            "status": RequirementStatus.COMPLETED,
            "review_fields": ReviewFields(
                proposed_supplier_id=11,
                proposed_supplier_name="可用供应商",
                supplier_contact_name="陈伟",
                supplier_contact_info="13910000001",
            ),
        }
    )
    client.seed_requirement(historical)
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(), current_action="ASSISTANT_CHAT"
    )
    await client.update_agent_state(
        identity=identity(),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            purchase_request_id=1,
            last_recommendations=(
                RecommendationReference(
                    reference_id="supplier:11",
                    kind="SUPPLIER_RECOMMENDATION",
                    label="可用供应商",
                ),
            ),
        ),
    )
    registry = ToolRegistry()
    registry.register(UpdateReviewDraftTool(client))
    agent = BuildingManagerAgent(
        AssistantSessionService(client), ToolExecutor(registry, max_result_chars=5000), client
    )
    ctx = context().model_copy(update={"conversation_id": conversation.conversation_id})

    recommendation = await agent.before_run(
        context=ctx,
        history=(AssistantMessage(role="user", content="1"),),
        user_text="1",
        external_message_id="om_supplier_1",
    )
    selected = await agent.before_run(
        context=ctx,
        history=(AssistantMessage(role="user", content="1"),),
        user_text="1",
        external_message_id="om_contact_choice_1",
    )

    assert isinstance(recommendation, AssistantTextResponse)
    assert "陈伟" in recommendation.text
    assert isinstance(selected, AssistantTextResponse)
    assert "已为您记录联系人和联系方式" in selected.text
    assert client._requirements[1].review_fields is not None
    assert client._requirements[1].review_fields.supplier_contact_name == "陈伟"
