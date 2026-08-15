# ruff: noqa: RUF001

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.assistant.agent import ProcurementAgent
from procurement_platform.application.assistant.capabilities import (
    DEFAULT_CAPABILITY_METADATA,
    CapabilityPolicy,
)
from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.presentation import LegacyToolResultPresenter
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.service import AssistantService
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.domain.assistant import AssistantTextResponse, AssistantTurn
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.user import CurrentUser, UserRole


def _backend(*roles: RoleCode) -> FakeBackendClient:
    return FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="Multi",
            mobile=None,
            status="ACTIVE",
            roles=tuple(UserRole(role_code=role) for role in roles),
            buildings=(),
        )
    )


def _service(backend: FakeBackendClient, *, turns: tuple[AssistantTurn, ...]) -> AssistantService:
    sessions = AssistantSessionService(backend)
    registry = ToolRegistry()
    executor = ToolExecutor(registry, max_result_chars=1000)
    runtime = AssistantRuntime(
        llm_client=FakeLlmClient(turns=turns),
        tool_registry=registry,
        tool_executor=executor,
        max_tool_steps=2,
    )
    policy = CapabilityPolicy(DEFAULT_CAPABILITY_METADATA)
    agent = ProcurementAgent(
        runtime=runtime,
        capability_policy=policy,
        session_service=sessions,
        result_presenter=LegacyToolResultPresenter(
            backend_client=backend,
            session_service=sessions,
        ),
    )
    return AssistantService(
        backend_client=backend,
        session_service=sessions,
        context_builder=AssistantContextBuilder(),
        procurement_agent=agent,
        max_history_messages=20,
    )


def _event(identifier: str, text: str) -> TextMessageEvent:
    return TextMessageEvent(
        event_id=f"event-{identifier}",
        external_user_id="ou_multi",
        external_message_id=identifier,
        chat_id="chat",
        text=text,
    )


@pytest.mark.asyncio
async def test_multi_role_text_does_not_require_role_selection() -> None:
    assistant = _service(
        _backend(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER),
        turns=(AssistantTurn(content="已查询待审核采购单"),),
    )

    response = await assistant.handle(_event("m1", "看看有哪些单子等我审核"))

    assert response == AssistantTextResponse(text="已查询待审核采购单")
    assert not hasattr(assistant, "_agent_router")
    assert not hasattr(assistant, "_role_intent_resolver")


@pytest.mark.asyncio
async def test_focused_role_is_retained_but_does_not_gate_text_agent() -> None:
    backend = _backend(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER)
    assistant = _service(backend, turns=(AssistantTurn(content="仍使用统一 Agent"),))

    switch = await assistant.handle(_event("switch", "切换到楼长"))
    response = await assistant.handle(_event("m2", "再看看我自己最近申请的采购单"))

    assert switch == AssistantTextResponse(
        text="已将默认展示角色切换为楼长；可用能力仍包含您的全部采购角色。"
    )
    assert response == AssistantTextResponse(text="仍使用统一 Agent")
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_multi")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.focused_role is RoleCode.BUILDING_MANAGER


@pytest.mark.asyncio
async def test_single_role_uses_same_procurement_agent_path() -> None:
    assistant = _service(
        _backend(RoleCode.WAREHOUSE_MANAGER),
        turns=(AssistantTurn(content="已查询待入库采购单"),),
    )

    assert await assistant.handle(_event("warehouse", "查询待入库单")) == (
        AssistantTextResponse(text="已查询待入库采购单")
    )


@pytest.mark.asyncio
async def test_user_without_workflow_role_is_rejected_before_llm() -> None:
    assistant = _service(_backend(RoleCode.ADMIN), turns=())

    assert await assistant.handle(_event("admin", "查询采购单")) == AssistantTextResponse(
        text="当前身份没有可用的采购助手角色。"
    )
