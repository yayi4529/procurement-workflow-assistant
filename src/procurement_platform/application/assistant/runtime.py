# ruff: noqa: RUF001

import logging
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from procurement_platform.application.assistant.context_composer import AgentContextComposer
from procurement_platform.application.assistant.grounding import GroundingDecision
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
    UnknownAssistantToolError,
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
        max_total_tool_calls: int = 24,
        tool_policy: object | None = None,
    ) -> None:
        if max_tool_steps < 1:
            raise ValueError("max_tool_steps must be positive")
        if max_total_tool_calls < 1:
            raise ValueError("max_total_tool_calls must be positive")
        self._llm_client = llm_client
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        # Deprecated TASK_01 compatibility argument. Authorization is now resolved before run().
        del tool_policy
        self._max_tool_steps = max_tool_steps
        self._max_total_tool_calls = max_total_tool_calls

    async def run(
        self,
        *,
        agent: RuntimeAgent,
        allowed_names: frozenset[str] | None = None,
        turn_context: AgentTurnContext,
        user_text: str,
        external_message_id: str,
        grounding: GroundingDecision | None = None,
    ) -> AssistantResponse:
        logger = logging.getLogger(__name__)
        agent_turn_id = str(uuid4())
        turn_started = perf_counter()
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
        mutation_seen = False
        total_tool_calls = 0
        grounding_satisfied = grounding is None or not grounding.required
        if grounding is not None and grounding.required and not grounding.relevant_tool_names:
            return AssistantTextResponse(
                text="当前身份没有可用于核实该请求的权威查询能力，无法安全回答。"
            )
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
                immediate_response: AssistantResponse | None = None
                terminal_result: AssistantToolResult | None = None
                for raw_call in turn.tool_calls:
                    call_started = perf_counter()
                    capability_call_id = str(uuid4())
                    side_effect = "UNKNOWN"
                    if total_tool_calls >= self._max_total_tool_calls:
                        result = AssistantToolResult(
                            status="TOOL_CALL_LIMIT_EXCEEDED",
                            user_message="本轮工具调用次数已达上限，请缩小请求范围后重试。",
                        )
                        tool_message = self._tool_executor.observation(
                            name=raw_call.name, tool_call_id=raw_call.id, result=result
                        )
                    else:
                        total_tool_calls += 1
                        try:
                            tool = self._tool_registry.get(raw_call.name)
                            side_effect = tool.side_effect
                        except UnknownAssistantToolError:
                            result = AssistantToolResult(
                                status="NOT_FOUND", user_message="未知工具"
                            )
                            tool_message = self._tool_executor.observation(
                                name=raw_call.name, tool_call_id=raw_call.id, result=result
                            )
                        else:
                            if mutation_seen and tool.side_effect == "MUTATE":
                                result = AssistantToolResult(
                                    status="MUTATION_LIMIT_EXCEEDED",
                                    user_message=(
                                        "Only one mutating tool may execute in one assistant turn."
                                    ),
                                )
                                tool_message = self._tool_executor.observation(
                                    name=raw_call.name, tool_call_id=raw_call.id, result=result
                                )
                            else:
                                if tool.side_effect == "MUTATE" and raw_call.name in allowed:
                                    mutation_seen = True
                                tool_message, result = await self._tool_executor.execute_result(
                                    name=raw_call.name,
                                    arguments_json=raw_call.arguments_json,
                                    tool_call_id=raw_call.id,
                                    context=context,
                                    allowed_names=allowed,
                                )
                    relevant_grounding_tool = (
                        grounding is not None and raw_call.name in grounding.relevant_tool_names
                    )
                    if relevant_grounding_tool and result.status in {
                        "SUCCESS",
                        "NOT_FOUND",
                        "MULTIPLE_MATCHES",
                    }:
                        grounding_satisfied = True
                    response = None
                    if grounding is None or not grounding.required or relevant_grounding_tool:
                        response = await agent.handle_tool_result(
                            result=result,
                            context=context,
                            external_message_id=external_message_id,
                        )
                    logger.info(
                        "assistant_capability_completed",
                        extra={
                            "agent_turn_id": agent_turn_id,
                            "capability_call_id": capability_call_id,
                            "conversation_id": context.conversation_id,
                            "capability_name": raw_call.name,
                            "side_effect": side_effect,
                            "status": result.status,
                            "result_type": type(result).__name__,
                            "latency_ms": round((perf_counter() - call_started) * 1000, 2),
                        },
                    )
                    if response is not None and immediate_response is None:
                        immediate_response = response
                    tool_messages.append(tool_message)
                    if tool_result_disposition(result) is ToolResultDisposition.TERMINATE:
                        terminal_result = result
                        break
                if terminal_result is not None:
                    return AssistantTextResponse(
                        text=terminal_result.user_message or "当前操作无法安全继续，请稍后重试。"
                    )
                if immediate_response is not None:
                    return immediate_response
                messages = (*messages, assistant_message, *tool_messages)
                continue
            if turn.content is not None and turn.content.strip():
                if not grounding_satisfied:
                    assert grounding is not None
                    content_retries += 1
                    relevant_names = ", ".join(sorted(grounding.relevant_tool_names))
                    messages = (
                        *messages,
                        AssistantMessage(role="assistant", content=turn.content),
                        AssistantMessage(
                            role="system",
                            content=(
                                "该请求涉及采购事实或推荐，必须先调用相关权威能力。"
                                f"请调用以下能力之一：{relevant_names}。"
                                "不要编造业务状态、供应商、产品、金额或历史记录。"
                            ),
                        ),
                    )
                    continue
                response = await agent.handle_content(
                    content=turn.content,
                    context=context,
                    user_text=user_text,
                    external_message_id=external_message_id,
                    retry_count=content_retries,
                )
                if response is not None:
                    logger.info(
                        "assistant_turn_completed",
                        extra={
                            "agent_turn_id": agent_turn_id,
                            "conversation_id": context.conversation_id,
                            "status": "success",
                            "latency_ms": round((perf_counter() - turn_started) * 1000, 2),
                        },
                    )
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
