from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.llm.echo_tool import EchoTool
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolCall,
    AssistantToolContext,
    AssistantToolResult,
    AssistantTurn,
)
from procurement_platform.domain.assistant_errors import (
    AssistantToolStepLimitError,
    LlmInvalidResponseError,
)
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser, UserRole


@dataclass
class RuntimeAgent:
    response_to_tool: AssistantResponse | None
    role: RoleCode = RoleCode.APPLICANT
    results: list[AssistantToolResult] = field(default_factory=list)

    def allowed_tool_names(self) -> frozenset[str]:
        return frozenset({"echo_tool"})

    def allowed_tool_names_for(self, user_text: str) -> frozenset[str]:
        del user_text
        return self.allowed_tool_names()

    def retry_tool_name(self) -> str | None:
        return None

    def prepare_tool_call(self, call: AssistantToolCall, *, user_text: str) -> AssistantToolCall:
        del user_text
        return call

    def build_messages(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
    ) -> tuple[AssistantMessage, ...]:
        del context
        return history

    async def before_run(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None:
        del context, history, user_text, external_message_id
        return None

    async def handle_content(
        self,
        *,
        content: str,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
        retry_count: int,
    ) -> AssistantResponse | None:
        del context, user_text, external_message_id, retry_count
        return AssistantTextResponse(text=content)

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        del context, external_message_id
        self.results.append(result)
        return self.response_to_tool


def runtime(
    turns: tuple[AssistantTurn, ...], *, max_steps: int = 3
) -> tuple[AssistantRuntime, FakeLlmClient]:
    registry = ToolRegistry()
    registry.register(EchoTool())
    llm = FakeLlmClient(turns=turns)
    executor = ToolExecutor(registry, max_result_chars=1000)
    return (
        AssistantRuntime(
            llm_client=llm,
            tool_registry=registry,
            tool_executor=executor,
            tool_policy=ToolPolicy(allow_fake_tools=True),
            max_tool_steps=max_steps,
        ),
        llm,
    )


def context() -> AssistantToolContext:
    user = CurrentUser(
        employee_id=1,
        name="Test",
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=RoleCode.APPLICANT, role_name="Applicant"),),
        buildings=(),
    )
    return AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id="ou_test",
        conversation_id=1,
        external_conversation_id="chat",
        external_message_id="message",
        current_time=datetime.now(UTC),
        timezone_name="Asia/Shanghai",
        current_user=user,
    )


def echo_call(identifier: str) -> AssistantToolCall:
    return AssistantToolCall(id=identifier, name="echo_tool", arguments_json='{"text":"hello"}')


@pytest.mark.asyncio
async def test_runtime_delegates_tool_result_and_returns_agent_response() -> None:
    engine, _ = runtime((AssistantTurn(tool_calls=(echo_call("one"),)),))
    agent = RuntimeAgent(response_to_tool=AssistantTextResponse(text="handled"))

    response = await engine.run(
        agent=agent,
        context=context(),
        history=(),
        user_text="hello",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="handled")
    assert len(agent.results) == 1


@pytest.mark.asyncio
async def test_runtime_puts_tool_message_back_and_continues() -> None:
    engine, llm = runtime(
        (AssistantTurn(tool_calls=(echo_call("one"),)), AssistantTurn(content="done"))
    )
    agent = RuntimeAgent(response_to_tool=None)

    response = await engine.run(
        agent=agent,
        context=context(),
        history=(),
        user_text="hello",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="done")
    assert llm.calls[1][-1].role == "tool"


@pytest.mark.asyncio
async def test_runtime_rejects_empty_llm_turn() -> None:
    engine, _ = runtime((AssistantTurn(),))

    with pytest.raises(LlmInvalidResponseError):
        await engine.run(
            agent=RuntimeAgent(response_to_tool=None),
            context=context(),
            history=(),
            user_text="hello",
            external_message_id="message",
        )


@pytest.mark.asyncio
async def test_runtime_enforces_tool_step_limit() -> None:
    engine, _ = runtime((AssistantTurn(tool_calls=(echo_call("one"),)),), max_steps=1)

    with pytest.raises(AssistantToolStepLimitError):
        await engine.run(
            agent=RuntimeAgent(response_to_tool=None),
            context=context(),
            history=(),
            user_text="hello",
            external_message_id="message",
        )
