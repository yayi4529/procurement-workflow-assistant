from datetime import UTC, datetime
from pathlib import Path

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.skills import MarkdownRoleSkillLoader
from procurement_platform.application.assistant.agent import ProcurementAgent
from procurement_platform.application.assistant.capabilities import CapabilityPolicy
from procurement_platform.application.assistant.presentation import LegacyToolResultPresenter
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tools import ToolExecutor
from procurement_platform.application.assistant.turn_context import AgentTurnContext
from procurement_platform.bootstrap.container import _build_capability_registry
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantTextResponse,
    AssistantToolContext,
    AssistantToolDefinition,
    AssistantTurn,
)
from procurement_platform.domain.assistant_errors import (
    LlmInvalidResponseError,
    LlmUnavailableError,
)
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.user import CurrentUser, UserRole


class RecordingLlmClient:
    def __init__(self, *turns: AssistantTurn) -> None:
        self._turns = iter(turns)
        self.tool_names: list[frozenset[str]] = []
        self.messages: list[tuple[AssistantMessage, ...]] = []

    async def complete(
        self,
        *,
        messages: tuple[AssistantMessage, ...],
        tools: tuple[AssistantToolDefinition, ...],
        tool_choice: str | None = None,
    ) -> AssistantTurn:
        del tool_choice
        self.messages.append(messages)
        self.tool_names.append(frozenset(tool.name for tool in tools))
        try:
            return next(self._turns)
        except StopIteration as exc:
            raise LlmUnavailableError("recording responses exhausted") from exc


def _user(*roles: RoleCode) -> CurrentUser:
    return CurrentUser(
        employee_id=1,
        name="Agent Test",
        mobile=None,
        status="ACTIVE",
        roles=tuple(UserRole(role_code=role) for role in roles),
        buildings=(),
    )


def _turn_context(user: CurrentUser, *, focused_role: RoleCode) -> AgentTurnContext:
    tool_context = AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id="ou_agent_test",
        conversation_id=1,
        external_conversation_id="oc_agent_test",
        external_message_id="om_agent_test",
        current_time=datetime(2026, 8, 15, tzinfo=UTC),
        timezone_name="Asia/Shanghai",
        current_user=user,
        active_requirement_id=None,
    )
    return AgentTurnContext(
        current_user=user,
        active_role=focused_role,
        session_state=None,
        active_requirement=None,
        recent_history=(AssistantMessage(role="user", content="查询采购单"),),
        current_recommendations=(),
        tool_context=tool_context,
    )


async def _agent(
    user: CurrentUser,
    llm: RecordingLlmClient,
    *,
    context_knowledge: str | None = None,
    use_role_skills: bool = False,
) -> tuple[ProcurementAgent, CapabilityPolicy]:
    backend = FakeBackendClient(user)
    await backend.get_or_create_agent_conversation(
        identity=PlatformIdentity.create(PlatformType.FEISHU, "ou_agent_test"),
        current_action="ASSISTANT_CHAT",
    )
    sessions = AssistantSessionService(backend)
    registry = _build_capability_registry(backend, llm if use_role_skills else None)
    policy = CapabilityPolicy(registry)
    runtime = AssistantRuntime(
        llm_client=llm,
        tool_registry=registry.tool_registry,
        tool_executor=ToolExecutor(registry.tool_registry, max_result_chars=10_000),
        max_tool_steps=2,
    )
    return (
        ProcurementAgent(
            runtime=runtime,
            capability_policy=policy,
            session_service=sessions,
            result_presenter=LegacyToolResultPresenter(
                backend_client=backend,
                session_service=sessions,
            ),
            context_knowledge=context_knowledge,
            role_skill_registry=(
                MarkdownRoleSkillLoader(Path(__file__).parents[2] / "skills")
                .load()
                .validate_capabilities(registry.tool_registry.registered_names)
                if use_role_skills
                else None
            ),
        ),
        policy,
    )


@pytest.mark.asyncio
async def test_role_skill_restricts_tools_and_injects_selected_workflow() -> None:
    user = _user(RoleCode.PURCHASER, RoleCode.APPLICANT)
    llm = RecordingLlmClient(AssistantTurn(content="完成"))
    agent, _ = await _agent(user, llm, use_role_skills=True)

    response = await agent.run(
        turn_context=_turn_context(user, focused_role=RoleCode.PURCHASER),
        user_text="\u4f9b\u5e94\u5546\u6392\u540d",
        external_message_id="skill-1",
    )

    assert isinstance(response, AssistantTextResponse)
    assert llm.tool_names[0] == frozenset({"recommend_suppliers_with_evidence"})
    system_messages = [
        message.content or "" for message in llm.messages[0] if message.role == "system"
    ]
    assert any('<workflow name="supplier-recommendation">' in item for item in system_messages)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    (
        RoleCode.APPLICANT,
        RoleCode.BUILDING_MANAGER,
        RoleCode.PURCHASER,
        RoleCode.WAREHOUSE_MANAGER,
    ),
)
async def test_single_procurement_agent_serves_each_role(role: RoleCode) -> None:
    user = _user(role)
    llm = RecordingLlmClient(AssistantTurn(content="完成"))
    agent, policy = await _agent(user, llm)

    response = await agent.run(
        turn_context=_turn_context(user, focused_role=role),
        user_text="解释采购流程中的角色分工",
        external_message_id="m1",
    )

    assert response == AssistantTextResponse(text="完成")
    assert llm.tool_names == [policy.allowed_names_for(user)]


@pytest.mark.asyncio
async def test_multi_role_union_is_not_cut_by_focused_role() -> None:
    user = _user(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER)
    llm = RecordingLlmClient(AssistantTurn(content="完成"))
    agent, policy = await _agent(user, llm)

    await agent.run(
        turn_context=_turn_context(user, focused_role=RoleCode.APPLICANT),
        user_text="解释多角色用户可以使用哪些助手能力",
        external_message_id="m1",
    )

    assert llm.tool_names == [policy.allowed_names_for(user)]
    assert llm.tool_names[0] == frozenset(
        {
            "search_purchase_requests",
            "get_purchase_request",
            "get_purchase_timeline",
            "recommend_products",
            "recommend_products_by_name",
            "update_applicant_draft",
            "update_multi_item_draft",
            "get_supplier_profile",
            "recommend_suppliers",
            "update_review_draft",
            "diagnose_procurement_need",
            "find_similar_purchases",
            "compare_products",
            "compare_suppliers",
            "search_assets",
            "resolve_asset",
            "get_asset",
            "get_asset_components",
            "get_asset_relations",
        }
    )


@pytest.mark.asyncio
async def test_explicit_purchase_intent_exposes_only_multi_item_draft_capability() -> None:
    user = _user(RoleCode.APPLICANT)
    llm = RecordingLlmClient(AssistantTurn(content=""))
    agent, _ = await _agent(user, llm)

    with pytest.raises(LlmInvalidResponseError):
        await agent.run(
            turn_context=_turn_context(user, focused_role=RoleCode.APPLICANT),
            user_text="我需要采购3块UPS蓄电池, 不指定品牌和型号",
            external_message_id="m1",
        )

    assert llm.tool_names[0] == frozenset({"update_multi_item_draft"})


@pytest.mark.asyncio
async def test_applicant_role_prompt_does_not_force_inject_fault_knowledge() -> None:
    user = _user(RoleCode.APPLICANT)
    llm = RecordingLlmClient(AssistantTurn(content="请确认故障部件和数量"))
    agent, _ = await _agent(
        user,
        llm,
        context_knowledge="UPS 高温可能涉及风扇和电容。",
    )

    await agent.run(
        turn_context=_turn_context(user, focused_role=RoleCode.APPLICANT),
        user_text="2号 UPS 高温报警",
        external_message_id="m1",
    )

    contents = [message.content or "" for message in llm.messages[0] if message.role == "system"]
    assert any("你是需求人采购助手" in content for content in contents)
    assert not any("<procurement_knowledge>" in content for content in contents)
    assert not any("UPS 高温可能涉及风扇和电容" in content for content in contents)


@pytest.mark.asyncio
async def test_fault_or_history_purchase_request_keeps_read_tools_available() -> None:
    user = _user(RoleCode.APPLICANT)
    llm = RecordingLlmClient(AssistantTurn(content="需要先查询历史"))
    agent, policy = await _agent(user, llm)

    await agent.run(
        turn_context=_turn_context(user, focused_role=RoleCode.APPLICANT),
        user_text="我要处理UPS故障, 不确定买什么",
        external_message_id="m1",
    )

    assert llm.tool_names[0] == policy.allowed_names_for(user)
    assert "find_similar_purchases" in llm.tool_names[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ("提交吧", "驳回", "开始采购", "确认完成"))
async def test_formal_action_language_cannot_expose_transition_capability(text: str) -> None:
    user = _user(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER, RoleCode.PURCHASER)
    llm = RecordingLlmClient(AssistantTurn(content="请在正式卡片中确认"))
    agent, _ = await _agent(user, llm)

    await agent.run(
        turn_context=_turn_context(user, focused_role=RoleCode.APPLICANT),
        user_text=text,
        external_message_id="m1",
    )

    assert not llm.tool_names[0].intersection(
        {
            "submit_review",
            "reject",
            "resubmit_review",
            "submit_purchaser",
            "start_purchase",
            "submit_warehouse",
            "complete",
        }
    )
    assert "正式提交" in (llm.messages[0][0].content or "")
