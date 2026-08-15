# ruff: noqa: RUF001

from typing import Protocol

from procurement_platform.application.assistant.context_composer import AgentContextComposer
from procurement_platform.application.assistant.tools import (
    ToolExecutor,
    ToolRegistry,
    ToolResultDisposition,
    tool_result_disposition,
)
from procurement_platform.application.assistant.turn_context import AgentTurnContext
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.assistant_errors import (
    AssistantToolStepLimitError,
    LlmInvalidResponseError,
)
from procurement_platform.ports.llm_client import LlmClient


class RuntimeAgent(Protocol):
    def build_messages(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        working_context: str | None = None,
    ) -> tuple[AssistantMessage, ...]: ...

    async def handle_content(
        self,
        *,
        content: str,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
        retry_count: int,
    ) -> AssistantResponse | None: ...

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None: ...


class AssistantRuntime:
    def __init__(
        self,
        *,
        llm_client: LlmClient,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        max_tool_steps: int,
        tool_policy: object | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        # Deprecated TASK_01 compatibility argument. Authorization is now resolved before run().
        del tool_policy
        self._max_tool_steps = max_tool_steps

    async def run(
        self,
        *,
        agent: RuntimeAgent,
        allowed_names: frozenset[str] | None = None,
        turn_context: AgentTurnContext,
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse:
        context = turn_context.tool_context
        messages = agent.build_messages(
            context=context,
            history=turn_context.recent_history,
            working_context=AgentContextComposer.compose(turn_context=turn_context),
        )
        # The fallback keeps direct legacy Runtime tests/adapters working. The production text
        # path always passes the CurrentUser multi-role union from ProcurementAgent.
        allowed = (
            allowed_names
            if allowed_names is not None
            else frozenset(getattr(agent, "tool_names", frozenset()))
        )
        definitions = self._tool_registry.definitions(allowed_names=allowed)
        content_retries = 0
        for _ in range(self._max_tool_steps):
            turn = await self._llm_client.complete(
                messages=messages,
                tools=definitions,
                tool_choice=None,
            )
            if turn.tool_calls:
                content_retries = 0
                assistant_message = AssistantMessage(
                    role="assistant", content=turn.content, tool_calls=turn.tool_calls
                )
                tool_messages: list[AssistantMessage] = []
                mutation_seen = False
                immediate_response: AssistantResponse | None = None
                terminal_result: AssistantToolResult | None = None
                for raw_call in turn.tool_calls:
                    tool = self._tool_registry.get(raw_call.name)
                    if mutation_seen and tool.side_effect == "MUTATE":
                        result = AssistantToolResult(
                            status="POLICY_BLOCKED",
                            user_message=(
                                "Only one mutating tool may execute in one assistant turn."
                            ),
                        )
                        tool_message = self._tool_executor.observation(
                            name=raw_call.name, tool_call_id=raw_call.id, result=result
                        )
                    else:
                        tool_message, result = await self._tool_executor.execute_result(
                            name=raw_call.name,
                            arguments_json=raw_call.arguments_json,
                            tool_call_id=raw_call.id,
                            context=context,
                            allowed_names=allowed,
                        )
                        mutation_seen = mutation_seen or tool.side_effect == "MUTATE"
                    response = await agent.handle_tool_result(
                        result=result,
                        context=context,
                        external_message_id=external_message_id,
                    )
                    if response is not None and immediate_response is None:
                        immediate_response = response
                    tool_messages.append(tool_message)
                    if tool_result_disposition(result) is ToolResultDisposition.TERMINATE:
                        terminal_result = terminal_result or result
                if immediate_response is not None:
                    return immediate_response
                if terminal_result is not None:
                    return AssistantTextResponse(
                        text=terminal_result.user_message or "当前操作无法安全继续，请稍后重试。"
                    )
                messages = (*messages, assistant_message, *tool_messages)
                continue
            if turn.content is not None and turn.content.strip():
                response = await agent.handle_content(
                    content=turn.content,
                    context=context,
                    user_text=user_text,
                    external_message_id=external_message_id,
                    retry_count=content_retries,
                )
                if response is not None:
                    return response
                content_retries += 1
                messages = (
                    *messages,
                    AssistantMessage(role="assistant", content=turn.content),
                    AssistantMessage(
                        role="system",
                        content="当前请求要求调用所提供的能力，请立即调用能力，不要只回复文本。",
                    ),
                )
                continue
            raise LlmInvalidResponseError("LLM returned neither content nor tool calls")
        raise AssistantToolStepLimitError("assistant tool step limit reached")
