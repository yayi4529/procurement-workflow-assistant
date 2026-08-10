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
        prepared = await agent.before_run(
            context=context,
            history=history,
            user_text=user_text,
            external_message_id=external_message_id,
        )
        if prepared is not None:
            return prepared
        messages = agent.build_messages(context=context, history=history)
        policy_allowed = self._tool_policy.allowed_tool_names(
            current_user=context.current_user, active_role=agent.role
        )
        allowed = policy_allowed & agent.allowed_tool_names_for(user_text)
        definitions = self._tool_registry.definitions(allowed_names=allowed)
        content_retries = 0
        requires_tool_call = getattr(agent, "requires_tool_call", None)
        initial_tool_required = bool(requires_tool_call and requires_tool_call(user_text))
        for _ in range(self._max_tool_steps):
            retry_tool_name = agent.retry_tool_name()
            retry_tools = tuple(
                tool
                for tool in definitions
                if retry_tool_name is not None and tool.name == retry_tool_name
            )
            turn = await self._llm_client.complete(
                messages=messages,
                tools=retry_tools if content_retries else definitions,
                tool_choice="required" if content_retries or initial_tool_required else None,
            )
            if turn.tool_calls:
                assistant_message = AssistantMessage(
                    role="assistant", content=turn.content, tool_calls=turn.tool_calls
                )
                tool_messages: list[AssistantMessage] = []
                for raw_call in turn.tool_calls:
                    call = agent.prepare_tool_call(raw_call, user_text=user_text)
                    tool_message, result = await self._tool_executor.execute_result(
                        name=call.name,
                        arguments_json=call.arguments_json,
                        tool_call_id=call.id,
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
