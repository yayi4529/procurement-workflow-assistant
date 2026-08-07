import json
import re

from procurement_platform.application.applicant.card_factory import ApplicantCardFactory
from procurement_platform.application.assistant.agent_tools import (
    PreparePurchasePrefillResult,
    RecommendProductOptionsResult,
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
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.assistant_errors import (
    AssistantToolStepLimitError,
    LlmInvalidResponseError,
)
from procurement_platform.domain.assistant_session import AgentSessionState
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
        starts_new_draft = self._starts_new_draft(event.text)
        active_state = None if starts_new_draft else state
        context = self._context_builder.build(
            identity=identity,
            conversation_id=conversation.conversation_id,
            external_message_id=event.external_message_id,
            external_conversation_id=event.chat_id,
            current_user=current_user,
            state=active_state,
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
        if starts_new_draft:
            history = history[-1:]
        messages = self._prompt_builder.build(context=context, history=history)
        allowed = self._tool_policy.allowed_tool_names(
            current_user=current_user, active_requirement=None
        )
        definitions = self._tool_registry.definitions(allowed_names=allowed)
        selection_index = self._selection_index(event.text, active_state)
        if selection_index is not None:
            references = (
                tuple(
                    item
                    for item in active_state.last_recommendations
                    if item.kind == "PRODUCT_RECOMMENDATION"
                )
                if active_state is not None
                else ()
            )
            if selection_index < 1 or selection_index > len(references):
                field = active_state.pending_field if active_state is not None else None
                text = self._invalid_selection_text(field, len(references))
                await self._append_reply(identity, conversation.conversation_id, event, text)
                return AssistantTextResponse(text=text)
            _, result = await self._tool_executor.execute_result(
                name="update_purchase_draft",
                arguments_json=json.dumps(
                    {"product_ref": references[selection_index - 1].reference_id},
                    ensure_ascii=False,
                ),
                tool_call_id="deterministic-product-selection",
                context=context,
                allowed_names=allowed,
            )
            if isinstance(result, UpdatePurchaseDraftResult):
                return await self._respond_to_draft_update(
                    result=result,
                    identity=identity,
                    context=context,
                    external_message_id=event.external_message_id,
                    allowed=allowed,
                )
        pending_arguments = self._pending_field_arguments(event.text, active_state)
        if pending_arguments is not None and "update_purchase_draft" in allowed:
            _, result = await self._tool_executor.execute_result(
                name="update_purchase_draft",
                arguments_json=json.dumps(pending_arguments, ensure_ascii=False),
                tool_call_id="deterministic-pending-field-answer",
                context=context,
                allowed_names=allowed,
            )
            if isinstance(result, UpdatePurchaseDraftResult):
                return await self._respond_to_draft_update(
                    result=result,
                    identity=identity,
                    context=context,
                    external_message_id=event.external_message_id,
                    allowed=allowed,
                )
        required_tool = self._required_tool(
            event.text, allowed, active_requirement_id=context.active_requirement_id
        )
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
                if isinstance(result, UpdatePurchaseDraftResult):
                    return await self._respond_to_draft_update(
                        result=result,
                        identity=identity,
                        context=context,
                        external_message_id=event.external_message_id,
                        allowed=allowed,
                    )
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
        if required_tool is not None and required_tool not in executed_tools:
            safe_text = (
                "我没有得到采购后端的确认, 因此没有声称已保存任何内容。请重新描述要保存的采购信息。"
            )
            await self._session_service.append(
                identity=identity,
                conversation_id=conversation.conversation_id,
                external_message_id=f"assistant:{event.external_message_id}",
                sender=AgentMessageSender.AGENT,
                content=safe_text,
            )
            return AssistantTextResponse(text=safe_text)
        raise AssistantToolStepLimitError("assistant tool step limit reached")

    @staticmethod
    def _required_tool(
        text: str, allowed: frozenset[str], *, active_requirement_id: int | None = None
    ) -> str | None:
        normalized = text.lower()
        query_terms = ("查询", "查一下", "查看", "列表", "详情", "状态", "时间线")
        purchase_terms = ("采购", "需求", "申请", "单据")
        if (
            "query_purchase_requests" in allowed
            and any(term in normalized for term in query_terms)
            and any(term in normalized for term in purchase_terms)
        ):
            return "query_purchase_requests"
        formal_action_terms = ("提交", "审批", "驳回", "开始采购", "完成入库", "确认完成")
        if any(term in normalized for term in formal_action_terms):
            return None
        draft_terms = (
            "购买",
            "采购申请",
            "采购需求",
            "申请采购",
            "整理",
            "草稿",
            "保存",
            "补充",
            "设备",
            "服务器",
            "型号",
            "数量",
            "品牌",
        )
        if "update_purchase_draft" in allowed and (
            any(term in normalized for term in draft_terms)
            or (active_requirement_id is not None and normalized not in {"你好", "您好", "在吗"})
        ):
            return "update_purchase_draft"
        return None

    @staticmethod
    def _starts_new_draft(text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        return any(
            marker in normalized
            for marker in ("新建采购", "新建一个采购", "新采购", "新的采购", "重新采购")
        )

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
        if (
            isinstance(result, UpdatePurchaseDraftResult)
            and result.status == "SUCCESS"
            and result.fields_complete
        ):
            assert result.requirement_id is not None
            detail = await self._backend_client.get_requirement(
                identity=identity, requirement_id=result.requirement_id
            )
            notice = "草稿已保存到采购后端, 字段已完整。请在正式需求卡片中确认并提交。"
            await self._session_service.append(
                identity=identity,
                conversation_id=conversation_id,
                external_message_id=f"assistant:{external_message_id}",
                sender=AgentMessageSender.AGENT,
                content=notice,
            )
            return AssistantInteractionResponse(
                view=ApplicantCardFactory().detail(detail, notice=notice)
            )
        if isinstance(result, UpdatePurchaseDraftResult) and result.user_message:
            await self._session_service.append(
                identity=identity,
                conversation_id=conversation_id,
                external_message_id=f"assistant:{external_message_id}",
                sender=AgentMessageSender.AGENT,
                content=result.user_message,
            )
            return AssistantTextResponse(text=result.user_message)
        if isinstance(result, PreparePurchasePrefillResult) and result.status == "SUCCESS":
            return AssistantInteractionResponse(view=self._prefill_view(result))
        return None

    async def _respond_to_draft_update(
        self,
        *,
        result: UpdatePurchaseDraftResult,
        identity: PlatformIdentity,
        context: AssistantToolContext,
        external_message_id: str,
        allowed: frozenset[str],
    ) -> AssistantResponse:
        if result.status != "SUCCESS":
            text = result.user_message or "采购草稿保存失败, 请稍后重试。"
            await self._session_service.append(
                identity=identity,
                conversation_id=context.conversation_id,
                external_message_id=f"assistant:{external_message_id}",
                sender=AgentMessageSender.AGENT,
                content=text,
            )
            return AssistantTextResponse(text=text)
        if result.fields_complete:
            response = await self._deterministic_response(
                result=result,
                identity=identity,
                conversation_id=context.conversation_id,
                external_message_id=external_message_id,
            )
            assert response is not None
            return response

        recommendation: RecommendProductOptionsResult | None = None
        if (
            result.next_missing_field in {"brand", "model"}
            and "recommend_product_options" in allowed
            and result.requirement_id is not None
        ):
            _, recommendation_result = await self._tool_executor.execute_result(
                name="recommend_product_options",
                arguments_json=json.dumps({"requirement_id": result.requirement_id}),
                tool_call_id="required-product-recommendation",
                context=context,
                allowed_names=allowed,
            )
            if isinstance(recommendation_result, RecommendProductOptionsResult):
                recommendation = recommendation_result
        text = self._draft_followup_text(result, recommendation)
        await self._session_service.append(
            identity=identity,
            conversation_id=context.conversation_id,
            external_message_id=f"assistant:{external_message_id}",
            sender=AgentMessageSender.AGENT,
            content=text,
        )
        return AssistantTextResponse(text=text)

    async def _append_reply(
        self,
        identity: PlatformIdentity,
        conversation_id: int,
        event: TextMessageEvent,
        text: str,
    ) -> None:
        assert event.external_message_id is not None
        await self._session_service.append(
            identity=identity,
            conversation_id=conversation_id,
            external_message_id=f"assistant:{event.external_message_id}",
            sender=AgentMessageSender.AGENT,
            content=text,
        )

    @staticmethod
    def _selection_index(text: str, state: AgentSessionState | None) -> int | None:
        pending_field = state.pending_field if state is not None else None
        recommendations = state.last_recommendations if state is not None else ()
        if pending_field not in {"brand", "model"} or not recommendations:
            return None
        normalized = re.sub(r"\s+", "", text)
        digit = re.fullmatch(r"(?:选)?([1-9]\d*)", normalized)
        if digit:
            return int(digit.group(1))
        words = {
            "第一个": 1,
            "第一": 1,
            "选第一个": 1,
            "选第一": 1,
            "第二个": 2,
            "第二": 2,
            "选第二个": 2,
            "选第二": 2,
            "第三个": 3,
            "第三": 3,
            "选第三个": 3,
            "选第三": 3,
        }
        return words.get(normalized)

    @staticmethod
    def _pending_field_arguments(
        text: str, state: AgentSessionState | None
    ) -> dict[str, str] | None:
        if state is None or state.purchase_request_id is None or state.pending_field is None:
            return None
        value = text.strip()
        if not value or len(value) > 100 or re.search(r"[,;\n\u3002\uff0c\uff1b]", value):
            return None
        supported_fields = {
            "device_profession",
            "device_name",
            "brand",
            "model",
            "quantity",
            "unit",
            "application_reason",
            "applicant_remark",
        }
        if state.pending_field not in supported_fields:
            return None
        return {state.pending_field: value}

    @staticmethod
    def _invalid_selection_text(field: str | None, count: int) -> str:
        label = {"brand": "品牌", "model": "型号"}.get(field or "", "选项")
        choices = "、".join(str(index) for index in range(1, count + 1))
        return f"当前有 {count} 个推荐选项, 请回复 {choices}, 或者直接告诉我您需要的{label}。"

    @classmethod
    def _draft_followup_text(
        cls,
        result: UpdatePurchaseDraftResult,
        recommendation: RecommendProductOptionsResult | None,
    ) -> str:
        labels = {
            "device_profession": "设备类型",
            "device_name": "设备名称",
            "brand": "品牌",
            "model": "型号",
            "quantity": "数量",
            "unit": "单位",
            "application_reason": "申请原因",
            "applicant_remark": "备注",
        }
        confirmations: list[str] = []
        quantity = result.updated_values.get("quantity")
        unit_value = result.updated_values.get("unit")
        for field in result.updated_fields:
            if field == "unit" and quantity is not None:
                continue
            value = result.updated_values.get(field)
            if value is None:
                continue
            if field == "quantity" and unit_value:
                value = f"{value} {unit_value}"
            confirmations.append(f"{labels.get(field, field)}为**{value}**")
        prefix = (
            f"好的, 已为您记录{'、'.join(confirmations)}。"
            if confirmations
            else "好的, 采购草稿已更新。"
        )
        next_field = result.next_missing_field
        label = labels.get(next_field or "", "下一项信息")
        question = f"请问您需要的**{label}**是什么呢?"
        if next_field == "application_reason":
            question = "请问本次采购的**申请原因**是什么呢?"
        if next_field not in {"brand", "model"}:
            return f"{prefix}\n\n{question}"
        if recommendation is not None and recommendation.status == "SUCCESS":
            values: list[str] = []
            for item in recommendation.candidates:
                value = item.brand if next_field == "brand" else item.model
                if value and value not in values:
                    values.append(value)
            if values:
                options = "\n".join(
                    f"{index}. {value}" for index, value in enumerate(values[:3], start=1)
                )
                return (
                    f"{prefix}\n\n{question}\n\n根据历史采购记录, 为您推荐:\n{options}"
                    f"\n\n请回复序号, 或者直接告诉我您需要的{label}。"
                )
        return f"{prefix}\n\n{question}\n\n暂未找到可用的推荐, 请直接告诉我您需要的{label}。"

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
