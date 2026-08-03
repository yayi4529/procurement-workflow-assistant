from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.prompt_builder import PromptBuilder
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.domain.assistant import AssistantMessage, AssistantTextResponse
from procurement_platform.domain.assistant_errors import (
    AssistantToolStepLimitError,
    LlmInvalidResponseError,
)
from procurement_platform.domain.enums import AgentMessageSender, PlatformType
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.ports.backend_client import BackendClient
from procurement_platform.ports.llm_client import LlmClient


class ProcurementAssistant:
    def __init__(
        self,
        *,
        backend_client: BackendClient,
        llm_client: LlmClient,
        session_service: AssistantSessionService,
        context_builder: AssistantContextBuilder,
        prompt_builder: PromptBuilder,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        tool_policy: ToolPolicy,
        max_tool_steps: int,
        max_history_messages: int,
    ) -> None:
        self._backend_client = backend_client
        self._llm_client = llm_client
        self._session_service = session_service
        self._context_builder = context_builder
        self._prompt_builder = prompt_builder
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._tool_policy = tool_policy
        self._max_tool_steps = max_tool_steps
        self._max_history_messages = max_history_messages

    async def handle(self, event: TextMessageEvent) -> AssistantTextResponse:
        if event.external_message_id is None:
            return AssistantTextResponse(text="无法识别消息。")
        identity = PlatformIdentity.create(PlatformType.FEISHU, event.external_user_id)
        current_user = await self._backend_client.get_current_user(identity=identity)
        conversation = await self._session_service.active(identity=identity)
        await self._session_service.append(
            identity=identity,
            conversation_id=conversation.conversation_id,
            external_message_id=event.external_message_id,
            sender=AgentMessageSender.USER,
            content=event.text,
        )
        try:
            state = await self._session_service.state(
                identity=identity, conversation_id=conversation.conversation_id
            )
        except Exception:
            state = None
        context = self._context_builder.build(
            identity=identity,
            conversation_id=conversation.conversation_id,
            external_message_id=event.external_message_id,
            external_conversation_id=event.chat_id,
            current_user=current_user,
            state=state,
        )
        page = await self._session_service.messages(
            identity=identity, conversation_id=conversation.conversation_id
        )
        history = tuple(
            AssistantMessage(
                role="user" if item.sender_type is AgentMessageSender.USER else "assistant",
                content=item.content,
            )
            for item in page.items[-self._max_history_messages :]
        )
        messages = self._prompt_builder.build(context=context, history=history)
        allowed = self._tool_policy.allowed_tool_names(
            current_user=current_user, active_requirement=None
        )
        definitions = self._tool_registry.definitions(allowed_names=allowed)
        for _ in range(self._max_tool_steps):
            turn = await self._llm_client.complete(messages=messages, tools=definitions)
            if turn.content is not None and turn.content.strip():
                await self._session_service.append(
                    identity=identity,
                    conversation_id=conversation.conversation_id,
                    external_message_id=f"assistant:{event.external_message_id}",
                    sender=AgentMessageSender.AGENT,
                    content=turn.content,
                )
                return AssistantTextResponse(text=turn.content)
            if not turn.tool_calls:
                raise LlmInvalidResponseError("LLM returned neither content nor tool calls")
            tool_messages: list[AssistantMessage] = []
            for call in turn.tool_calls:
                tool_messages.append(
                    await self._tool_executor.execute(
                        name=call.name,
                        arguments_json=call.arguments_json,
                        tool_call_id=call.id,
                        context=context,
                        allowed_names=allowed,
                    )
                )
            messages = (*messages, *tool_messages)
        raise AssistantToolStepLimitError("assistant tool step limit reached")
