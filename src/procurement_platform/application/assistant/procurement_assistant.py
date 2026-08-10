import json

from procurement_platform.application.applicant.card_factory import ApplicantCardFactory
from procurement_platform.application.assistant.agent_tools import (
    PreparePurchasePrefillResult,
    QueryPurchaseRequestsResult,
    RecommendProductOptionsResult,
    UpdatePurchaseDraftResult,
)
from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.prompt_builder import PromptBuilder
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.application.status_labels import requirement_status_label
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolCall,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.assistant_errors import (
    AssistantToolStepLimitError,
    LlmInvalidResponseError,
    LlmUnavailableError,
)
from procurement_platform.domain.enums import (
    AgentMessageSender,
    PlatformType,
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.interaction import (
    ActionButton,
    InteractionView,
    KeyValueField,
    KeyValueSection,
    MarkdownBlock,
)
from procurement_platform.domain.user import CurrentUser
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
        read_only_query = self._is_read_only_query(event.text)
        if read_only_query:
            definitions = tuple(
                tool for tool in definitions if tool.name == "query_purchase_requests"
            )
        execution_allowed = (
            frozenset(tool.name for tool in definitions) if read_only_query else allowed
        )
        if read_only_query and self._is_history_summary_query(event.text):
            query_call = AssistantToolCall(
                id="deterministic-history-query",
                name="query_purchase_requests",
                arguments_json=json.dumps({"operation": "SEARCH", "result_limit": 10}),
            )
            _, query_result = await self._tool_executor.execute_result(
                name="query_purchase_requests",
                arguments_json=query_call.arguments_json,
                tool_call_id=query_call.id,
                context=context,
                allowed_names=execution_allowed,
            )
            if isinstance(query_result, QueryPurchaseRequestsResult):
                try:
                    narrative_turn = await self._llm_client.complete(
                        messages=(
                            *messages,
                            AssistantMessage(
                                role="system",
                                content=(
                                    "以下是系统刚从采购后端获得的只读查询结果 JSON: "
                                    f"{query_result.model_dump_json()}。"
                                    "请仅依据该结果自然回复用户。"
                                    "总数只能使用 total_count; 不得声称保存、修改或创建了采购草稿。"
                                    "回复保持简洁, 卡片将由系统另外渲染。"
                                ),
                            ),
                        ),
                        tools=(),
                        tool_choice=None,
                    )
                    narrative = (
                        narrative_turn.content.strip()
                        if narrative_turn.content is not None and narrative_turn.content.strip()
                        else None
                    )
                except LlmUnavailableError:
                    narrative = None
                return await self._history_card_response(
                    result=query_result,
                    identity=identity,
                    conversation_id=conversation.conversation_id,
                    external_message_id=event.external_message_id,
                    narrative=narrative,
                )
            safe_text = query_result.user_message or "历史采购记录查询失败, 请稍后重试。"
            await self._append_reply(identity, conversation.conversation_id, event, safe_text)
            return AssistantTextResponse(text=safe_text)
        query_tool_required = read_only_query and bool(definitions)
        content_retries = 0
        retry_pending_draft = await self._should_retry_pending_draft(
            identity=identity,
            active_requirement_id=context.active_requirement_id,
            pending_field=state.pending_field if state is not None else None,
            text=event.text,
            draft_tool_allowed="update_purchase_draft" in allowed and not read_only_query,
        )
        for _ in range(self._max_tool_steps):
            retry_tools = tuple(
                tool for tool in definitions if tool.name == "update_purchase_draft"
            )
            turn = await self._llm_client.complete(
                messages=messages,
                tools=retry_tools if content_retries > 0 else definitions,
                tool_choice=("required" if content_retries > 0 or query_tool_required else None),
            )
            if turn.content is not None and turn.content.strip():
                # Only retry a structured write for a verified DRAFT whose
                # currently pending field is being answered.  A plain-text
                # answer to a list, count, detail, or status query must never
                # be turned into a draft write.
                if retry_pending_draft and content_retries == 0:
                    content_retries += 1
                    messages = (
                        *messages,
                        AssistantMessage(role="assistant", content=turn.content),
                        AssistantMessage(
                            role="system",
                            content=(
                                "当前会话有一张后端确认的未完成草稿, 用户正在补充待填字段。"
                                "你刚才没有调用工具;"
                                "请根据当前待补字段和用户最新消息, 立即调用 update_purchase_draft, "
                                "不要回复保存承诺或普通文本。"
                            ),
                        ),
                    )
                    continue
                # If the model still declines the tool after the correction,
                # preserve a short answer for the single pending field instead
                # of claiming that it was saved.  The normal tool remains the
                # only writer and still performs backend validation/versioning.
                pending_field = state.pending_field if state is not None else None
                if (
                    content_retries > 0
                    and pending_field
                    in {
                        "device_profession",
                        "device_name",
                        "brand",
                        "model",
                        "quantity",
                        "unit",
                        "application_reason",
                        "applicant_remark",
                    }
                    and len(event.text.strip()) <= 100
                ):
                    fallback_call = AssistantToolCall(
                        id="pending-field-fallback",
                        name="update_purchase_draft",
                        arguments_json=json.dumps(
                            {pending_field: event.text.strip()}, ensure_ascii=False
                        ),
                    )
                    tool_message, result = await self._tool_executor.execute_result(
                        name=fallback_call.name,
                        arguments_json=fallback_call.arguments_json,
                        tool_call_id=fallback_call.id,
                        context=context,
                        allowed_names=execution_allowed,
                    )
                    del tool_message
                    if isinstance(result, UpdatePurchaseDraftResult):
                        return await self._respond_to_draft_update(
                            result=result,
                            identity=identity,
                            context=context,
                            external_message_id=event.external_message_id,
                            allowed=allowed,
                        )
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
                query_tool_required = False
                tool_message, result = await self._tool_executor.execute_result(
                    name=call.name,
                    arguments_json=call.arguments_json,
                    tool_call_id=call.id,
                    context=context,
                    allowed_names=execution_allowed,
                )
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
                    current_user=current_user,
                )
                if deterministic is not None:
                    return deterministic
                tool_messages.append(tool_message)
            messages = (*messages, assistant_message, *tool_messages)
        raise AssistantToolStepLimitError("assistant tool step limit reached")

    async def _should_retry_pending_draft(
        self,
        *,
        identity: PlatformIdentity,
        active_requirement_id: int | None,
        pending_field: str | None,
        text: str,
        draft_tool_allowed: bool,
    ) -> bool:
        if (
            not draft_tool_allowed
            or active_requirement_id is None
            or pending_field
            not in {
                "device_profession",
                "device_name",
                "brand",
                "model",
                "quantity",
                "unit",
                "application_reason",
                "applicant_remark",
            }
            or not self._looks_like_pending_field_reply(text)
        ):
            return False
        try:
            detail = await self._backend_client.get_requirement(
                identity=identity, requirement_id=active_requirement_id
            )
        except Exception:
            # This is a write safeguard: when the current draft cannot be
            # verified, retain the read-only response path instead of guessing.
            return False
        return detail.status is RequirementStatus.DRAFT

    @staticmethod
    def _looks_like_pending_field_reply(text: str) -> bool:
        candidate = text.strip()
        if not candidate or len(candidate) > 100 or "?" in candidate or "\uff1f" in candidate:
            return False
        query_markers = (
            "多少",
            "查询",
            "查一下",
            "查看",
            "列表",
            "详情",
            "状态",
            "历史",
            "提交了",
            "采购申请",
            "统计",
        )
        return not any(marker in candidate for marker in query_markers)

    @staticmethod
    def _is_read_only_query(text: str) -> bool:
        normalized = text.strip()
        query_markers = ("多少", "查询", "查一下", "查看", "列表", "详情", "状态", "历史", "统计")
        purchase_markers = ("采购", "申请", "需求", "单据")
        return any(marker in normalized for marker in query_markers) and any(
            marker in normalized for marker in purchase_markers
        )

    @staticmethod
    def _is_history_summary_query(text: str) -> bool:
        normalized = text.strip()
        if "详情" in normalized or "状态" in normalized or "时间线" in normalized:
            return False
        return any(
            marker in normalized for marker in ("多少", "一共", "统计", "列表", "历史", "之前")
        )

    async def _deterministic_response(
        self,
        *,
        result: AssistantToolResult,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
        current_user: CurrentUser,
    ) -> AssistantResponse | None:
        if (
            isinstance(result, QueryPurchaseRequestsResult)
            and result.total_count is not None
            and RoleCode.APPLICANT in {role.role_code for role in current_user.roles}
        ):
            return await self._history_card_response(
                result=result,
                identity=identity,
                conversation_id=conversation_id,
                external_message_id=external_message_id,
            )
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
                current_user=context.current_user,
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
                source_label = "采购白名单" if next_field == "brand" else "历史采购记录"
                return (
                    f"{prefix}\n\n{question}\n\n根据{source_label}, 为您推荐:\n{options}"
                    f"\n\n请回复序号, 或者直接告诉我您需要的{label}。"
                )
        return f"{prefix}\n\n{question}\n\n暂未找到可用的推荐, 请直接告诉我您需要的{label}。"

    async def _history_card_response(
        self,
        *,
        result: QueryPurchaseRequestsResult,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
        narrative: str | None = None,
    ) -> AssistantResponse:
        total = result.total_count or 0
        text = narrative or (
            f"已查询到您可见的采购申请共 {total} 条。点击下方单据可查看具体需求和当前状态。"
        )
        await self._session_service.append(
            identity=identity,
            conversation_id=conversation_id,
            external_message_id=f"assistant:{external_message_id}",
            sender=AgentMessageSender.AGENT,
            content=text,
        )
        lines = [text, "", f"共 **{total}** 条采购申请"]
        actions: list[ActionButton] = []
        for item in result.records:
            lines.append(
                f"- {item.requirement_no} | {item.device_name or '未填写'} | "
                f"{requirement_status_label(item.status)}"
            )
            actions.append(
                ActionButton(
                    action_id="applicant.open",
                    label=f"查看 {item.requirement_no}",
                    value={"requirement_id": item.requirement_id},
                )
            )
        if not result.records and result.requirement_id is not None and result.requirement_no:
            status = (
                requirement_status_label(result.status_value)
                if result.status_value is not None
                else "状态以详情为准"
            )
            lines.append(f"- {result.requirement_no} | {status}")
            actions.append(
                ActionButton(
                    action_id="applicant.open",
                    label=f"查看 {result.requirement_no}",
                    value={"requirement_id": result.requirement_id},
                )
            )
        if total > len(result.records):
            lines.append(f"当前展示前 {len(result.records)} 条")
        return AssistantInteractionResponse(
            view=InteractionView(
                title="我的采购申请",
                subtitle="后端实时查询结果",
                elements=(MarkdownBlock(markdown="\n".join(lines)),),
                actions=tuple(actions),
            )
        )

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
