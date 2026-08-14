# ruff: noqa: RUF001

from procurement_platform.application.assistant.agents.protocol import RoleAgent
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantResponse,
    AssistantToolContext,
)
from procurement_platform.domain.assistant_errors import (
    AssistantToolStepLimitError,
    LlmInvalidResponseError,
)
from procurement_platform.ports.llm_client import LlmClient


class AssistantRuntime:
    def __init__(
        self,
        *,
        llm_client: LlmClient,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        tool_policy: ToolPolicy,
        max_tool_steps: int,
    ) -> None:
        self._llm_client = llm_client
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._tool_policy = tool_policy
        self._max_tool_steps = max_tool_steps

    async def run(
        self,
        *,
        agent: RoleAgent,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse:
        context_builder = getattr(agent, "working_context", None)
        working_context = await context_builder(context) if context_builder else None
        if context_builder:
            messages = agent.build_messages(
                context=context, history=history, working_context=working_context
            )
        else:
            messages = agent.build_messages(context=context, history=history)
        policy_allowed = self._tool_policy.allowed_tool_names(
            current_user=context.current_user, active_role=agent.role
        )
        allowed = policy_allowed & agent.tool_names
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
                for raw_call in turn.tool_calls:
                    tool = self._tool_registry.get(raw_call.name)
                    if mutation_seen and tool.side_effect == "MUTATE":
                        break
                    tool_message, result = await self._tool_executor.execute_result(
                        name=raw_call.name,
                        arguments_json=raw_call.arguments_json,
                        tool_call_id=raw_call.id,
                        context=context,
                        allowed_names=allowed,
                    )
                    response = await agent.handle_tool_result(
                        result=result,
                        context=context,
                        external_message_id=external_message_id,
                    )
                    if response is not None:
                        return response
                    tool_messages.append(tool_message)
                    mutation_seen = mutation_seen or tool.side_effect == "MUTATE"
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
                        content="当前角色要求本轮调用所提供的工具，请立即调用工具，不要只回复文本。",
                    ),
                )
                continue
            raise LlmInvalidResponseError("LLM returned neither content nor tool calls")
        raise AssistantToolStepLimitError("assistant tool step limit reached")
