from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
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
        return next(self._turns)


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
    user: CurrentUser, llm: RecordingLlmClient
) -> tuple[ProcurementAgent, CapabilityPolicy]:
    backend = FakeBackendClient(user)
    await backend.get_or_create_agent_conversation(
        identity=PlatformIdentity.create(PlatformType.FEISHU, "ou_agent_test"),
        current_action="ASSISTANT_CHAT",
    )
    sessions = AssistantSessionService(backend)
    registry = _build_capability_registry(backend)
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
        ),
        policy,
    )


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
        user_text="查询采购单",
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
        user_text="看看有哪些单子等我审核",
        external_message_id="m1",
    )

    assert llm.tool_names == [policy.allowed_names_for(user)]
    assert llm.tool_names[0] == frozenset(
        {
            "search_purchase_requests",
            "get_purchase_request",
            "get_purchase_timeline",
            "recommend_products",
            "update_applicant_draft",
            "get_supplier_profile",
            "recommend_suppliers",
            "update_review_draft",
            "diagnose_procurement_need",
            "find_similar_purchases",
            "compare_products",
            "compare_suppliers",
        }
    )


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
