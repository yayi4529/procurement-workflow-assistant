from datetime import UTC, date, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.assistant.agent_tools import (
    UpdateReviewDraftArgs,
    UpdateReviewDraftTool,
)
from procurement_platform.application.assistant.agents.building_manager import BuildingManagerAgent
from procurement_platform.application.assistant.context_composer import AgentContextComposer
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.supplier_recommendation import (
    RecommendSuppliersForRequirementArgs,
    RecommendSuppliersForRequirementTool,
)
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.application.assistant.turn_context import AgentTurnContext
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantTextResponse,
    AssistantToolCall,
    AssistantToolContext,
    AssistantTurn,
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


def context(*, conversation_id: int = 1) -> AssistantToolContext:
    return AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id="ou_manager",
        conversation_id=conversation_id,
        external_conversation_id="oc_1",
        external_message_id="om_1",
        current_time=datetime.now(UTC),
        timezone_name="Asia/Shanghai",
        current_user=manager(),
        active_requirement_id=1,
    )


async def turn_context(client: FakeBackendClient, conversation_id: int) -> AgentTurnContext:
    tool_context = context(conversation_id=conversation_id)
    state = await client.get_agent_state(identity=identity(), conversation_id=conversation_id)
    return AgentTurnContext(
        current_user=tool_context.current_user,
        active_role=RoleCode.BUILDING_MANAGER,
        session_state=state,
        active_requirement=await client.get_requirement(identity=identity(), requirement_id=1),
        recent_history=(),
        current_recommendations=state.last_recommendations,
        tool_context=tool_context,
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
                application_reason="网络扩容",
            ),
            missing_fields=(),
            allowed_actions=(AllowedRequirementAction.UPDATE_REVIEW_FIELDS,),
        )
    )
    for supplier_id, supplier_name in ((11, "供应商A"), (12, "供应商B"), (13, "供应商C")):
        client.seed_supplier(
            SupplierDetail(
                supplier_id=supplier_id,
                supplier_name=supplier_name,
                blacklist=SupplierBlacklistSummary(active=False),
                contract_contact_info=f"138000000{supplier_id}",
            )
        )
    client.purchase_records.extend(
        PurchaseRecord(
            requirement_id=90 + index,
            requirement_no=f"PR-{90 + index}",
            device_name="交换机",
            brand="华为",
            status=RequirementStatus.COMPLETED,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            quantity="2",
            actual_total_price=str(200 + index * 20),
            purchased_at=datetime(2026, 7, index + 1, tzinfo=UTC),
            created_at=datetime(2026, 6, index + 1, tzinfo=UTC),
        )
        for index, (supplier_id, supplier_name) in enumerate(
            ((11, "供应商A"), (12, "供应商B"), (13, "供应商C"))
        )
    )
    return client


async def seed_recommendations(
    client: FakeBackendClient, *, kind: str = "SUPPLIER_RECOMMENDATION"
) -> int:
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(), current_action="ASSISTANT_CHAT"
    )
    await client.update_agent_state(
        identity=identity(),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            purchase_request_id=1,
            last_recommendations=tuple(
                RecommendationReference(
                    reference_id=f"supplier:{supplier_id}", kind=kind, label=supplier_name
                )
                for supplier_id, supplier_name in (
                    (11, "供应商A"),
                    (12, "供应商B"),
                    (13, "供应商C"),
                )
            ),
        ),
    )
    return conversation.conversation_id


def build_runtime(
    client: FakeBackendClient, turns: tuple[AssistantTurn, ...]
) -> tuple[AssistantRuntime, FakeLlmClient, BuildingManagerAgent]:
    registry = ToolRegistry()
    registry.register(RecommendSuppliersForRequirementTool(client))
    registry.register(UpdateReviewDraftTool(client))
    executor = ToolExecutor(registry, max_result_chars=10_000)
    llm = FakeLlmClient(turns=turns)
    agent = BuildingManagerAgent(AssistantSessionService(client), executor, client)
    return (
        AssistantRuntime(
            llm_client=llm,
            tool_registry=registry,
            tool_executor=executor,
            tool_policy=ToolPolicy(),
            max_tool_steps=4,
        ),
        llm,
        agent,
    )


@pytest.mark.asyncio
async def test_manager_supplier_recommendation_rechecks_backend_and_saves_references() -> None:
    client = backend()
    conversation_id = await seed_recommendations(client)

    result = await RecommendSuppliersForRequirementTool(client).execute(
        args=RecommendSuppliersForRequirementArgs(requirement_id=1),
        context=context(conversation_id=conversation_id),
    )
    saved = await client.get_agent_state(identity=identity(), conversation_id=conversation_id)

    assert result.status == "SUCCESS"
    assert len(result.candidates) == 3
    assert result.candidates[0].blacklist_status == "NORMAL"
    assert result.candidates[0].historical_unit_prices
    assert saved.last_recommendations[0].kind == "SUPPLIER_RECOMMENDATION"
    assert client.call_counts["get_current_user"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("selection_index", "supplier_id"), ((1, 11), (3, 13)))
async def test_review_draft_selection_index_resolves_real_recommendation(
    selection_index: int, supplier_id: int
) -> None:
    client = backend()
    conversation_id = await seed_recommendations(client)

    result = await UpdateReviewDraftTool(client).execute(
        args=UpdateReviewDraftArgs(requirement_id=1, selection_index=selection_index),
        context=context(conversation_id=conversation_id),
    )

    assert result.status == "SUCCESS"
    assert client._requirements[1].review_fields is not None
    assert client._requirements[1].review_fields.proposed_supplier_id == supplier_id
    assert client.call_counts["submit_purchaser"] == 0


@pytest.mark.asyncio
async def test_review_draft_selection_index_out_of_range_does_not_write() -> None:
    client = backend()
    conversation_id = await seed_recommendations(client)

    result = await UpdateReviewDraftTool(client).execute(
        args=UpdateReviewDraftArgs(requirement_id=1, selection_index=4),
        context=context(conversation_id=conversation_id),
    )

    assert result.status == "INVALID_ARGUMENTS"
    assert client._requirements[1].review_fields is None
    assert client.call_counts["update_review_fields"] == 0


@pytest.mark.asyncio
async def test_review_draft_selection_index_without_recommendations_fails_safely() -> None:
    client = backend()
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(), current_action="ASSISTANT_CHAT"
    )

    result = await UpdateReviewDraftTool(client).execute(
        args=UpdateReviewDraftArgs(requirement_id=1, selection_index=1),
        context=context(conversation_id=conversation.conversation_id),
    )

    assert result.status == "INVALID_ARGUMENTS"
    assert client.call_counts["update_review_fields"] == 0


@pytest.mark.asyncio
async def test_review_draft_selection_index_rejects_wrong_recommendation_kind() -> None:
    client = backend()
    conversation_id = await seed_recommendations(client, kind="PRODUCT_RECOMMENDATION")

    result = await UpdateReviewDraftTool(client).execute(
        args=UpdateReviewDraftArgs(requirement_id=1, selection_index=1),
        context=context(conversation_id=conversation_id),
    )

    assert result.status == "INVALID_ARGUMENTS"
    assert client.call_counts["update_review_fields"] == 0


@pytest.mark.asyncio
async def test_supplier_recommendation_success_returns_to_llm_observation_loop() -> None:
    client = backend()
    conversation_id = await seed_recommendations(client)
    runtime, llm, agent = build_runtime(
        client,
        (
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(
                        id="recommend",
                        name="recommend_suppliers_for_requirement",
                        arguments_json='{"requirement_id":1}',
                    ),
                )
            ),
            AssistantTurn(content="供应商A、B、C均来自真实历史记录, 请选择希望继续使用的一家。"),
        ),
    )

    response = await runtime.run(
        agent=agent,
        turn_context=await turn_context(client, conversation_id),
        user_text="推荐几个供应商",
        external_message_id="om_recommend",
    )

    assert isinstance(response, AssistantTextResponse)
    assert len(llm.calls) == 2
    assert llm.calls[1][-1].role == "tool"
    assert "candidates" in (llm.calls[1][-1].content or "")


@pytest.mark.asyncio
async def test_natural_language_selection_is_understood_by_llm_and_saved_by_tool() -> None:
    client = backend()
    conversation_id = await seed_recommendations(client)
    runtime, _, agent = build_runtime(
        client,
        (
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(
                        id="select",
                        name="update_review_draft",
                        arguments_json='{"requirement_id":1,"selection_index":1}',
                    ),
                )
            ),
            AssistantTurn(content="供应商已保存, 仍有审核字段需要补充。"),
        ),
    )

    response = await runtime.run(
        agent=agent,
        turn_context=await turn_context(client, conversation_id),
        user_text="就第一个吧。",
        external_message_id="om_select",
    )

    assert isinstance(response, AssistantTextResponse)
    assert client._requirements[1].review_fields is not None
    assert client._requirements[1].review_fields.proposed_supplier_id == 11


@pytest.mark.asyncio
async def test_llm_can_save_multiple_review_fields_in_one_tool_call() -> None:
    client = backend()
    conversation_id = await seed_recommendations(client)
    tool = UpdateReviewDraftTool(client)

    result = await tool.execute(
        args=UpdateReviewDraftArgs(
            requirement_id=1,
            selection_index=1,
            supplier_contact_name="张工",
            supplier_contact_info="13800138000",
            expected_arrival_date=date(2026, 8, 20),
            estimated_unit_price="12800",
            need_contract=True,
            contract_type="采购合同",
            payment_method="验收后付款",
        ),
        context=context(conversation_id=conversation_id),
    )

    assert result.status == "SUCCESS"
    assert result.fields_complete is True
    assert set(result.updated_fields) >= {
        "proposed_supplier_id",
        "supplier_contact_name",
        "supplier_contact_info",
        "expected_arrival_date",
        "estimated_unit_price",
        "need_contract",
    }
    assert result.updated_values["expected_arrival_date"] == "2026-08-20"
    assert client.call_counts["update_review_fields"] == 1


@pytest.mark.asyncio
async def test_ambiguous_supplier_wording_is_not_guessed_by_python() -> None:
    client = backend()
    await seed_recommendations(client)
    _, _, _ = build_runtime(client, ())

    assert not hasattr(BuildingManagerAgent, "before_run")
    assert client.call_counts["update_review_fields"] == 0


@pytest.mark.asyncio
async def test_complete_review_draft_returns_formal_card_without_transition() -> None:
    client = backend()
    conversation_id = await seed_recommendations(client)
    _, _, agent = build_runtime(client, ())
    result = await UpdateReviewDraftTool(client).execute(
        args=UpdateReviewDraftArgs(
            requirement_id=1,
            selection_index=1,
            supplier_contact_name="张工",
            supplier_contact_info="13800138000",
            estimated_unit_price="12800",
            need_contract=False,
            payment_method="验收后付款",
            expected_arrival_date=date(2026, 8, 20),
        ),
        context=context(conversation_id=conversation_id),
    )

    response = await agent.handle_tool_result(
        result=result,
        context=context(conversation_id=conversation_id),
        external_message_id="om_complete",
    )

    assert result.fields_complete is True
    assert isinstance(response, AssistantInteractionResponse)
    assert client._requirements[1].status is RequirementStatus.PENDING_REVIEW
    assert client.call_counts["reject_requirement"] == 0
    assert client.call_counts["submit_purchaser"] == 0


def test_building_manager_agent_contains_no_natural_language_parser_constants() -> None:
    assert not hasattr(BuildingManagerAgent, "_SELECTIONS")
    assert not hasattr(BuildingManagerAgent, "_SELECTION_ALIASES")
    assert not hasattr(BuildingManagerAgent, "_NEGATIVE_RESPONSES")


@pytest.mark.asyncio
async def test_building_manager_working_context_contains_backend_review_facts() -> None:
    client = backend()
    conversation_id = await seed_recommendations(client)
    rendered = AgentContextComposer.compose(
        turn_context=await turn_context(client, conversation_id)
    )

    assert '"requirement_no":"PR-1"' in rendered
    assert "application_reason" in rendered
    assert "网络扩容" in rendered
    assert '"review_draft":{}' in rendered
    assert "供应商A" in rendered
    assert "supplier:11" not in rendered
