from procurement_platform.application.applicant.card_factory import ApplicantCardFactory
from procurement_platform.application.assistant.agent_tools import (
    PreparePurchasePrefillResult,
    UpdatePurchaseDraftResult,
)
from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.prompt_builder import PromptBuilder
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolResult,
)
from procurement_platform.domain.assistant_errors import (
    AssistantToolStepLimitError,
    LlmInvalidResponseError,
)
from procurement_platform.domain.enums import AgentMessageSender, PlatformType
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.interaction import InteractionView, KeyValueField, KeyValueSection
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

    async def handle(self, event: TextMessageEvent) -> AssistantResponse:
        if event.external_message_id is None:
            return AssistantTextResponse(text="无法识别消息。")
        identity = PlatformIdentity.create(PlatformType.FEISHU, event.external_user_id)
        current_user = await self._backend_client.get_current_user(identity=identity)
        conversation = await self._session_service.active(identity=identity)
        write = await self._session_service.append(
            identity=identity,
            conversation_id=conversation.conversation_id,
            external_message_id=event.external_message_id,
            sender=AgentMessageSender.USER,
            content=event.text,
        )
        if write.duplicate:
            previous = await self._session_service.messages(
                identity=identity, conversation_id=conversation.conversation_id
            )
            prior_reply = next(
                (
                    item.content
                    for item in reversed(previous.items)
                    if item.external_message_id == f"assistant:{event.external_message_id}"
                ),
                None,
            )
            if prior_reply is not None:
                return AssistantTextResponse(text=prior_reply)
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
        visible_items = page.items
        target_index = next(
            (
                index
                for index, item in enumerate(visible_items)
                if item.external_message_id == event.external_message_id
            ),
            len(visible_items) - 1,
        )
        visible_items = visible_items[: target_index + 1]
        history = tuple(
            AssistantMessage(
                role="user" if item.sender_type is AgentMessageSender.USER else "assistant",
                content=item.content,
            )
            for item in visible_items[-self._max_history_messages :]
        )
        messages = self._prompt_builder.build(context=context, history=history)
        allowed = self._tool_policy.allowed_tool_names(
            current_user=current_user, active_requirement=None
        )
        definitions = self._tool_registry.definitions(allowed_names=allowed)
        required_tool = self._required_tool(event.text, allowed)
        executed_tools: set[str] = set()
        for _ in range(self._max_tool_steps):
            turn = await self._llm_client.complete(messages=messages, tools=definitions)
            if turn.content is not None and turn.content.strip():
                if required_tool is not None and required_tool not in executed_tools:
                    messages = (
                        *messages,
                        AssistantMessage(role="assistant", content=turn.content),
                        AssistantMessage(
                            role="system",
                            content=(
                                f"该请求必须先调用 {required_tool}。"
                                "不要先回复执行承诺;请立即调用工具。"
                            ),
                        ),
                    )
                    continue
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
            assistant_message = AssistantMessage(
                role="assistant", content=turn.content, tool_calls=turn.tool_calls
            )
            tool_messages: list[AssistantMessage] = []
            for call in turn.tool_calls:
                tool_message, result = await self._tool_executor.execute_result(
                    name=call.name,
                    arguments_json=call.arguments_json,
                    tool_call_id=call.id,
                    context=context,
                    allowed_names=allowed,
                )
                executed_tools.add(call.name)
                deterministic = await self._deterministic_response(
                    result=result,
                    identity=identity,
                    conversation_id=conversation.conversation_id,
                    external_message_id=event.external_message_id,
                )
                if deterministic is not None:
                    return deterministic
                tool_messages.append(tool_message)
            messages = (*messages, assistant_message, *tool_messages)
        raise AssistantToolStepLimitError("assistant tool step limit reached")

    @staticmethod
    def _required_tool(text: str, allowed: frozenset[str]) -> str | None:
        normalized = text.lower()
        query_terms = ("查询", "查一下", "查看", "列表", "详情", "状态", "时间线")
        purchase_terms = ("采购", "需求", "申请", "单据")
        if (
            "query_purchase_requests" in allowed
            and any(term in normalized for term in query_terms)
            and any(term in normalized for term in purchase_terms)
        ):
            return "query_purchase_requests"
        return None

    async def _deterministic_response(
        self,
        *,
        result: AssistantToolResult,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if result.exact_render_required and result.user_message:
            await self._session_service.append(
                identity=identity,
                conversation_id=conversation_id,
                external_message_id=f"assistant:{external_message_id}",
                sender=AgentMessageSender.AGENT,
                content=result.user_message,
            )
            return AssistantTextResponse(text=result.user_message)
        if isinstance(result, UpdatePurchaseDraftResult) and result.fields_complete:
            assert result.requirement_id is not None
            detail = await self._backend_client.get_requirement(
                identity=identity, requirement_id=result.requirement_id
            )
            return AssistantInteractionResponse(
                view=ApplicantCardFactory().detail(
                    detail, notice="草稿字段已完整, 请在正式卡片中确认后提交。"
                )
            )
        if isinstance(result, PreparePurchasePrefillResult) and result.status == "SUCCESS":
            return AssistantInteractionResponse(view=self._prefill_view(result))
        return None

    @staticmethod
    def _prefill_view(result: PreparePurchasePrefillResult) -> InteractionView:
        return InteractionView(
            title="采购员预填推荐",
            subtitle="仅展示建议, 不会自动保存或提交",
            elements=(
                KeyValueSection(
                    fields=tuple(
                        KeyValueField(
                            label=item.field_name,
                            value=(
                                item.value
                                if item.value is not None
                                else "/".join(item.alternatives) or "待补充"
                            ),
                        )
                        for item in result.fields
                    )
                ),
            ),
        )
