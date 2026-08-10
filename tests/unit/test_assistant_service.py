# ruff: noqa: RUF001

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.assistant.agent_router import AgentRouter
from procurement_platform.application.assistant.agents.base import BasicRoleAgent
from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.service import AssistantService
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.domain.assistant import (
    AssistantClarificationResponse,
    AssistantTextResponse,
)
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.user import CurrentUser, UserRole


class ApplicantStub(BasicRoleAgent):
    role = RoleCode.APPLICANT
    role_prompt = "applicant"
    tool_names = frozenset()


class PurchaserStub(BasicRoleAgent):
    role = RoleCode.PURCHASER
    role_prompt = "purchaser"
    tool_names = frozenset()


def service(backend: FakeBackendClient) -> AssistantService:
    sessions = AssistantSessionService(backend)
    registry = ToolRegistry()
    executor = ToolExecutor(registry, max_result_chars=1000)
    runtime = AssistantRuntime(
        llm_client=FakeLlmClient(turns=()),
        tool_registry=registry,
        tool_executor=executor,
        tool_policy=ToolPolicy(),
        max_tool_steps=2,
    )
    return AssistantService(
        backend_client=backend,
        session_service=sessions,
        context_builder=AssistantContextBuilder(),
        agent_router=AgentRouter((ApplicantStub(sessions), PurchaserStub(sessions))),
        runtime=runtime,
        max_history_messages=20,
    )


def event(identifier: str, text: str) -> TextMessageEvent:
    return TextMessageEvent(
        event_id=f"event-{identifier}",
        external_user_id="ou_multi",
        external_message_id=identifier,
        chat_id="chat",
        text=text,
    )


@pytest.mark.asyncio
async def test_multi_role_selection_is_explicit_and_persisted() -> None:
    backend = FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="Multi",
            mobile=None,
            status="ACTIVE",
            roles=(
                UserRole(role_code=RoleCode.APPLICANT, role_name="Applicant"),
                UserRole(role_code=RoleCode.PURCHASER, role_name="Purchaser"),
            ),
            buildings=(),
        )
    )
    assistant = service(backend)

    first = await assistant.handle(event("m1", "帮我处理采购"))
    second = await assistant.handle(event("m2", "2"))

    assert isinstance(first, AssistantClarificationResponse)
    assert [option.value for option in first.options] == ["APPLICANT", "PURCHASER"]
    assert second == AssistantTextResponse(text="已选择采购员助手，请继续告诉我需要处理的内容。")
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_multi")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.focused_role is RoleCode.PURCHASER

    switched = await assistant.handle(event("m3", "切换角色 需求人"))
    assert switched == AssistantTextResponse(
        text="已切换到需求人助手，请继续告诉我需要处理的内容。"
    )
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.focused_role is RoleCode.APPLICANT
