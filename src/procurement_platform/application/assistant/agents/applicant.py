# ruff: noqa: RUF001, RUF003

import json
import logging
import re
from typing import ClassVar

from procurement_platform.application.applicant.card_factory import ApplicantCardFactory
from procurement_platform.application.assistant.agent_tools import (
    QueryPurchaseRequestsResult,
    RecommendProductOptionsResult,
    UpdatePurchaseDraftResult,
)
from procurement_platform.application.assistant.agents.base import BasicRoleAgent
from procurement_platform.application.assistant.prompts.applicant import APPLICANT_PROMPT
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tools import ToolExecutor
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
from procurement_platform.domain.assistant_errors import LlmUnavailableError
from procurement_platform.domain.assistant_session import AgentSessionStateUpdate
from procurement_platform.domain.enums import PlatformType, RequirementStatus, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import ActionButton, InteractionView, MarkdownBlock
from procurement_platform.ports.backend_client import BackendClient
from procurement_platform.ports.llm_client import LlmClient

logger = logging.getLogger(__name__)


class ApplicantAgent(BasicRoleAgent):
    role = RoleCode.APPLICANT
    role_prompt = APPLICANT_PROMPT
    tool_names = frozenset(
        {"query_purchase_requests", "recommend_product_options", "update_purchase_draft"}
    )

    _RECOMMENDABLE_FIELDS = frozenset({"brand", "model"})

    _FIELD_LABELS: ClassVar[dict[str, str]] = {
        "device_profession": "设备类型",
        "device_name": "设备名称",
        "brand": "品牌",
        "model": "型号",
        "quantity": "数量",
        "unit": "单位",
        "application_reason": "申请原因",
        "applicant_remark": "备注",
    }

    _QUERY_MARKERS = (
        "多少",
        "查询",
        "查一下",
        "查看",
        "列表",
        "详情",
        "状态",
        "历史",
        "统计",
        "一共",
        "之前",
        "时间线",
    )

    # These markers mean that even if the sentence contains “查看/查询”,
    # it is not a pure read-only request.
    _MUTATION_OR_RECOMMENDATION_MARKERS = (
        "修改",
        "改成",
        "改为",
        "更新",
        "补充",
        "填写",
        "保存",
        "新建",
        "重新建",
        "再建",
        "推荐",
        "换成",
        "调整",
    )

    # Python only acts as a safety net for *explicit* new-draft wording.
    # Broader natural-language intent remains the LLM's responsibility.
    _EXPLICIT_NEW_DRAFT_MARKERS = (
        "新建一张采购草稿",
        "新建采购草稿",
        "重新建一张采购草稿",
        "再建一张采购草稿",
        "另外新建一张采购草稿",
        "新建另一张采购草稿",
    )

    _NEW_PURCHASE_REQUEST_MARKERS = (
        "我要购买",
        "我想购买",
        "我要采购",
        "我想采购",
        "帮我购买",
        "帮我买",
        "帮我采购",
        "需要购买",
        "需要采购",
    )

    _NON_VALUE_REPLIES = frozenset(
        {
            "不知道",
            "不清楚",
            "不确定",
            "还不知道",
            "还没想好",
            "暂时不确定",
            "暂时没有",
            "没有",
            "先不填",
            "先跳过",
            "跳过",
            "随便",
            "都可以",
            "无所谓",
            "算了",
            "不用了",
        }
    )

    _SELECTION_ALIASES: ClassVar[dict[str, int]] = {
        "1": 1,
        "第一个": 1,
        "第1个": 1,
        "选1": 1,
        "选第一个": 1,
        "选择1": 1,
        "选择第一个": 1,
        "2": 2,
        "第二个": 2,
        "第2个": 2,
        "选2": 2,
        "选第二个": 2,
        "选择2": 2,
        "选择第二个": 2,
        "3": 3,
        "第三个": 3,
        "第3个": 3,
        "选3": 3,
        "选第三个": 3,
        "选择3": 3,
        "选择第三个": 3,
    }

    _CANCEL_MARKERS = ("取消", "算了", "不用了", "不填了", "先不填", "停止填写", "结束填写")
    _STATUS_MARKERS: ClassVar[dict[str, RequirementStatus]] = {
        "草稿": RequirementStatus.DRAFT,
        "待审核": RequirementStatus.PENDING_REVIEW,
        "被驳回": RequirementStatus.REJECTED,
        "已驳回": RequirementStatus.REJECTED,
        "待采购": RequirementStatus.PENDING_PURCHASE,
        "采购中": RequirementStatus.PURCHASING,
        "待入库": RequirementStatus.PENDING_WAREHOUSE,
        "已完成": RequirementStatus.COMPLETED,
    }

    def __init__(
        self,
        *,
        backend_client: BackendClient,
        llm_client: LlmClient,
        session_service: AssistantSessionService,
        tool_executor: ToolExecutor,
    ) -> None:
        super().__init__(session_service)
        self._backend_client = backend_client
        self._llm_client = llm_client
        self._tool_executor = tool_executor

    def allowed_tool_names_for(self, user_text: str) -> frozenset[str]:
        if self._is_cancel_intent(user_text):
            return frozenset()
        # Restrict tools only for a *pure* read-only request.
        # Mixed requests such as “查看这个需求，把数量改成 3 台” must keep
        # update_purchase_draft available.
        if self._is_pure_read_only_query(user_text):
            return frozenset({"query_purchase_requests"})
        return self.allowed_tool_names()

    def retry_tool_name(self) -> str | None:
        return "update_purchase_draft"

    def requires_tool_call(self, user_text: str) -> bool:
        return self._explicit_new_draft_text(user_text)

    def prepare_tool_call(
        self,
        call: AssistantToolCall,
        *,
        user_text: str,
    ) -> AssistantToolCall:
        if call.name != "update_purchase_draft" or not self._explicit_new_draft_text(user_text):
            return call

        try:
            arguments = json.loads(call.arguments_json)
        except json.JSONDecodeError:
            return call

        if not isinstance(arguments, dict):
            return call

        arguments["start_new"] = True
        arguments.pop("requirement_id", None)
        return call.model_copy(update={"arguments_json": json.dumps(arguments, ensure_ascii=False)})

    def build_messages(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
    ) -> tuple[AssistantMessage, ...]:
        is_new_draft = self._is_explicit_new_draft(history)

        # Keep only the active exchange. When explicitly creating a new draft,
        # do not expose stale field values from the prior draft to the model.
        visible_history = history[-1:] if is_new_draft else history[-2:]
        messages = super().build_messages(context=context, history=visible_history)

        if not is_new_draft:
            return messages

        return (
            messages[0],
            AssistantMessage(
                role="system",
                content=(
                    "用户本轮明确要求新建采购草稿。调用 update_purchase_draft 时必须传 "
                    "start_new=true，并且只提取用户当前消息明确表达的采购字段；"
                    "不得复用历史草稿中的任何字段值。"
                ),
            ),
            *messages[1:],
        )

    @classmethod
    def _is_explicit_new_draft(
        cls,
        history: tuple[AssistantMessage, ...],
    ) -> bool:
        if not history or history[-1].role != "user" or history[-1].content is None:
            return False
        return cls._explicit_new_draft_text(history[-1].content)

    @classmethod
    def _explicit_new_draft_text(cls, text: str) -> bool:
        normalized = text.strip()
        if any(marker in normalized for marker in cls._EXPLICIT_NEW_DRAFT_MARKERS):
            return True
        if cls._is_pure_read_only_query(normalized):
            return False
        return any(marker in normalized for marker in cls._NEW_PURCHASE_REQUEST_MARKERS)

    async def before_run(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if self._is_cancel_intent(user_text):
            return await self._cancel_pending_collection(
                context=context, external_message_id=external_message_id
            )
        # Only historical/list/statistical pure queries bypass normal tool-calling.
        # Detail/status queries still go through the standard agent path.
        if not self._is_history_summary_query(user_text):
            return None

        _, result = await self._tool_executor.execute_result(
            name="query_purchase_requests",
            arguments_json=json.dumps(self._history_query_arguments(user_text), ensure_ascii=False),
            tool_call_id="deterministic-history-query",
            context=context,
            allowed_names=frozenset({"query_purchase_requests"}),
        )

        if not isinstance(result, QueryPurchaseRequestsResult):
            text = result.user_message or "历史采购记录查询失败，请稍后重试。"
            await self._append_reply(context, external_message_id, text)
            return AssistantTextResponse(text=text)

        narrative = await self._history_narrative(
            result=result,
            context=context,
            history=history,
        )
        return await self._history_card_response(
            result=result,
            context=context,
            external_message_id=external_message_id,
            narrative=narrative,
        )

    async def _cancel_pending_collection(
        self, *, context: AssistantToolContext, external_message_id: str
    ) -> AssistantResponse:
        identity = self._identity(context)
        try:
            state = await self._session_service.state(
                identity=identity, conversation_id=context.conversation_id
            )
            update = AgentSessionStateUpdate.model_validate(
                state.model_dump(
                    exclude={"conversation_id", "expires_in_seconds", "restored_from_snapshot"}
                )
            ).model_copy(
                update={
                    "pending_field": None,
                    "focused_field": None,
                    "awaiting_confirmation": False,
                }
            )
            await self._session_service.save_state(
                identity=identity, conversation_id=context.conversation_id, state=update
            )
        except Exception:
            logger.warning("Unable to clear pending applicant field", exc_info=True)
        text = "好的，已停止本轮草稿信息填写；已有草稿不会被提交或删除。"
        await self._append_reply(context, external_message_id, text)
        return AssistantTextResponse(text=text)

    @classmethod
    def _history_query_arguments(cls, text: str) -> dict[str, object]:
        arguments: dict[str, object] = {"operation": "SEARCH", "result_limit": 10}
        for marker, status in cls._STATUS_MARKERS.items():
            if marker in text:
                arguments["status"] = status.value
                break
        for marker in ("今天", "昨天", "本周", "上周", "本月", "上月", "今年"):
            if marker in text:
                arguments["time_expression"] = marker
                break
        for field, pattern in (
            ("device_name", r"设备(?:名称)?(?:为|是|[:：])\s*([^，。！？,!?]+)"),
            ("brand", r"品牌(?:为|是|[:：])\s*([^，。！？,!?]+)"),
            ("model", r"型号(?:为|是|[:：])\s*([^，。！？,!?]+)"),
        ):
            match = re.search(pattern, text)
            if match:
                arguments[field] = match.group(1).strip()
        return arguments

    async def _history_narrative(
        self,
        *,
        result: QueryPurchaseRequestsResult,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
    ) -> str | None:
        try:
            turn = await self._llm_client.complete(
                messages=(
                    *self.build_messages(context=context, history=history),
                    AssistantMessage(
                        role="system",
                        content=(
                            "以下是采购后端只读结果 JSON: "
                            f"{result.model_dump_json()}。仅依据该结果简洁回复；"
                            "总数只能使用 total_count，不得声称保存或创建草稿。"
                        ),
                    ),
                ),
                tools=(),
                tool_choice=None,
            )
        except LlmUnavailableError:
            return None

        if turn.content is None:
            return None

        narrative = turn.content.strip()
        return narrative or None

    async def handle_content(
        self,
        *,
        content: str,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
        retry_count: int,
    ) -> AssistantResponse | None:
        if retry_count == 0 and self._explicit_new_draft_text(user_text):
            return None
        if retry_count == 0:
            pending_field = await self._pending_field_for_fallback(context, user_text)
            if pending_field is not None:
                arguments = self._pending_field_arguments(
                    pending_field=pending_field,
                    user_text=user_text,
                )
                if arguments is not None:
                    _, result = await self._tool_executor.execute_result(
                        name="update_purchase_draft",
                        arguments_json=json.dumps(arguments, ensure_ascii=False),
                        tool_call_id="pending-field-fallback",
                        context=context,
                        allowed_names=self.allowed_tool_names(),
                    )
                    if isinstance(result, UpdatePurchaseDraftResult):
                        return await self._respond_to_draft_update(
                            result=result,
                            context=context,
                            external_message_id=external_message_id,
                        )

        return await super().handle_content(
            content=content,
            context=context,
            user_text=user_text,
            external_message_id=external_message_id,
            retry_count=retry_count,
        )

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if isinstance(result, UpdatePurchaseDraftResult):
            return await self._respond_to_draft_update(
                result=result,
                context=context,
                external_message_id=external_message_id,
            )

        if isinstance(result, QueryPurchaseRequestsResult) and result.total_count is not None:
            return await self._history_card_response(
                result=result,
                context=context,
                external_message_id=external_message_id,
            )

        return await super().handle_tool_result(
            result=result,
            context=context,
            external_message_id=external_message_id,
        )

    async def _respond_to_draft_update(
        self,
        *,
        result: UpdatePurchaseDraftResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse:
        if result.status != "SUCCESS":
            return await self._draft_update_failure_response(
                result=result,
                context=context,
                external_message_id=external_message_id,
            )

        if result.fields_complete:
            return await self._completed_draft_response(
                result=result,
                context=context,
                external_message_id=external_message_id,
            )

        recommendation = await self._recommend_for_missing_field(
            result=result,
            context=context,
        )
        text = self._draft_followup_text(result, recommendation)
        await self._append_reply(context, external_message_id, text)
        return AssistantTextResponse(text=text)

    async def _draft_update_failure_response(
        self,
        *,
        result: UpdatePurchaseDraftResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse:
        text = result.user_message or "采购草稿保存失败，请稍后重试。"
        await self._append_reply(context, external_message_id, text)
        return AssistantTextResponse(text=text)

    async def _completed_draft_response(
        self,
        *,
        result: UpdatePurchaseDraftResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse:
        assert result.requirement_id is not None

        detail = await self._backend_client.get_requirement(
            identity=self._identity(context),
            requirement_id=result.requirement_id,
        )
        notice = "草稿已保存到采购后端，字段已完整。请在正式需求卡片中确认并提交。"
        await self._append_reply(context, external_message_id, notice)
        return AssistantInteractionResponse(
            view=ApplicantCardFactory().detail(detail, notice=notice)
        )

    async def _recommend_for_missing_field(
        self,
        *,
        result: UpdatePurchaseDraftResult,
        context: AssistantToolContext,
    ) -> RecommendProductOptionsResult | None:
        if (
            result.next_missing_field not in self._RECOMMENDABLE_FIELDS
            or result.requirement_id is None
        ):
            return None

        _, recommendation_result = await self._tool_executor.execute_result(
            name="recommend_product_options",
            arguments_json=json.dumps({"requirement_id": result.requirement_id}),
            tool_call_id="required-product-recommendation",
            context=context,
            allowed_names=self.allowed_tool_names(),
        )

        if isinstance(recommendation_result, RecommendProductOptionsResult):
            return recommendation_result
        return None

    async def _pending_field_for_fallback(
        self,
        context: AssistantToolContext,
        text: str,
    ) -> str | None:
        try:
            state = await self._session_service.state(
                identity=self._identity(context),
                conversation_id=context.conversation_id,
            )
        except Exception:
            logger.warning(
                "Unable to load applicant assistant session for pending-field fallback",
                exc_info=True,
            )
            return None

        pending_field = state.pending_field
        if (
            context.active_requirement_id is None
            or pending_field is None
            or not self._looks_like_pending_field_reply(
                pending_field=pending_field,
                text=text,
            )
        ):
            return None

        try:
            detail = await self._backend_client.get_requirement(
                identity=self._identity(context),
                requirement_id=context.active_requirement_id,
            )
        except Exception:
            logger.warning(
                "Unable to load active requirement for pending-field fallback",
                exc_info=True,
            )
            return None

        if detail.status is not RequirementStatus.DRAFT:
            return None

        return pending_field

    @classmethod
    def _pending_field_arguments(
        cls,
        *,
        pending_field: str,
        user_text: str,
    ) -> dict[str, object] | None:
        cleaned = cls._clean_user_value(user_text)
        if not cleaned:
            return None

        # Only brand/model use product recommendations. A plain "1" while the
        # pending field is quantity must remain quantity=1, not selection_index=1.
        if pending_field in cls._RECOMMENDABLE_FIELDS:
            selection_index = cls._selection_index(cleaned)
            if selection_index is not None:
                return {"selection_index": selection_index}

        if pending_field == "quantity":
            match = re.fullmatch(r"(?:需要|要|采购)?\s*(\d+(?:\.\d+)?)\s*(?:台|个|套|件)?", cleaned)
            return {"quantity": match.group(1)} if match else None

        if pending_field == "unit":
            match = re.fullmatch(
                r"(?:单位(?:是|为)?|按)?\s*(台|个|套|件|箱|组|块|只|支|米)", cleaned
            )
            return {"unit": match.group(1)} if match else None

        if pending_field in {"device_profession", "device_name", "brand", "model"}:
            value = re.sub(
                rf"^(?:{re.escape(cls._FIELD_LABELS[pending_field])})?(?:是|为|[:：])?\s*",
                "",
                cleaned,
            )
            return {pending_field: value} if value else None

        return {pending_field: cleaned}

    @classmethod
    def _looks_like_pending_field_reply(
        cls,
        *,
        pending_field: str,
        text: str,
    ) -> bool:
        candidate = cls._clean_user_value(text)

        if not candidate:
            return False

        # Keep fallback deliberately conservative. If it is unclear whether the
        # text is an answer, let the normal LLM path handle it.
        max_length = 200 if pending_field in {"application_reason", "applicant_remark"} else 100
        if len(candidate) > max_length:
            return False

        if "?" in candidate or "？" in candidate:
            return False

        if candidate in cls._NON_VALUE_REPLIES or cls._is_cancel_intent(candidate):
            return False

        if cls._explicit_new_draft_text(candidate):
            return False

        if cls._is_pure_read_only_query(candidate):
            return False

        if any(marker in candidate for marker in cls._MUTATION_OR_RECOMMENDATION_MARKERS):
            # A sentence like “品牌改成华为，数量改成3台” should return to
            # the LLM so all explicit fields can be extracted in one tool call.
            return False

        return True

    @staticmethod
    def _clean_user_value(text: str) -> str:
        return text.strip().rstrip("。！？!?")

    @classmethod
    def _selection_index(cls, text: str) -> int | None:
        normalized = cls._clean_user_value(text).replace(" ", "")
        return cls._SELECTION_ALIASES.get(normalized)

    @classmethod
    def _is_cancel_intent(cls, text: str) -> bool:
        normalized = cls._clean_user_value(text).replace(" ", "")
        return any(marker in normalized for marker in cls._CANCEL_MARKERS)

    @staticmethod
    def _identity(context: AssistantToolContext) -> PlatformIdentity:
        return PlatformIdentity.create(
            PlatformType(context.platform_type),
            context.platform_user_id,
        )

    @classmethod
    def _is_pure_read_only_query(cls, text: str) -> bool:
        normalized = text.strip()

        has_query_intent = any(marker in normalized for marker in cls._QUERY_MARKERS)
        if not has_query_intent:
            return False

        # Require procurement-domain wording so ordinary conversational
        # questions do not accidentally disable write tools.
        has_procurement_subject = any(
            marker in normalized for marker in ("采购", "申请", "需求", "单据", "采购单")
        )
        if not has_procurement_subject:
            return False

        has_mutation_or_recommendation = any(
            marker in normalized for marker in cls._MUTATION_OR_RECOMMENDATION_MARKERS
        )
        return not has_mutation_or_recommendation

    @classmethod
    def _is_history_summary_query(cls, text: str) -> bool:
        if not cls._is_pure_read_only_query(text):
            return False

        if any(marker in text for marker in ("详情", "状态", "时间线")):
            return False

        return any(marker in text for marker in ("多少", "一共", "统计", "列表", "历史", "之前"))

    @classmethod
    def _draft_followup_text(
        cls,
        result: UpdatePurchaseDraftResult,
        recommendation: RecommendProductOptionsResult | None,
    ) -> str:
        prefix = cls._confirmation_prefix(result)
        next_field = result.next_missing_field
        label = cls._FIELD_LABELS.get(next_field or "", "下一项信息")
        question = cls._followup_question(next_field=next_field, label=label)

        if next_field not in cls._RECOMMENDABLE_FIELDS:
            return f"{prefix}\n\n{question}"

        values = cls._recommendation_values(
            next_field=next_field,
            recommendation=recommendation,
        )
        if not values:
            return f"{prefix}\n\n{question}\n\n暂未找到可用的推荐，请直接告诉我您需要的{label}。"

        options = "\n".join(f"{index}. {value}" for index, value in enumerate(values, 1))
        source = cls._recommendation_source_label(recommendation)
        return (
            f"{prefix}\n\n{question}\n\n"
            f"根据{source}，为您推荐：\n"
            f"{options}\n\n"
            f"请回复序号，或者直接告诉我您需要的{label}。"
        )

    @classmethod
    def _confirmation_prefix(
        cls,
        result: UpdatePurchaseDraftResult,
    ) -> str:
        confirmations: list[str] = []

        quantity = result.updated_values.get("quantity")
        unit_value = result.updated_values.get("unit")

        for field in result.updated_fields:
            # If quantity was updated together with unit, render “2 台” once.
            if field == "unit" and quantity is not None:
                continue

            value = result.updated_values.get(field)
            if value is None:
                continue

            if field == "quantity" and unit_value:
                value = f"{value} {unit_value}"

            label = cls._FIELD_LABELS.get(field, field)
            confirmations.append(f"{label}为**{value}**")

        if not confirmations:
            return "好的，采购草稿已更新。"

        return f"好的，已为您记录{'、'.join(confirmations)}。"

    @staticmethod
    def _followup_question(
        *,
        next_field: str | None,
        label: str,
    ) -> str:
        if next_field == "application_reason":
            return "请问本次采购的**申请原因**是什么呢？"
        if next_field == "device_profession":
            return "请问该设备属于什么**设备类型**呢？"
        if next_field == "device_name":
            return "请问您需要采购的**设备名称**是什么呢？"
        if next_field == "quantity":
            return "请问您需要采购的**数量**是多少呢？"
        if next_field == "unit":
            return "请问采购数量的**单位**是什么呢？"
        if next_field == "applicant_remark":
            return "请问还有需要补充的**备注**吗？"
        return f"请问您需要的**{label}**是什么呢？"

    @classmethod
    def _recommendation_values(
        cls,
        *,
        next_field: str | None,
        recommendation: RecommendProductOptionsResult | None,
    ) -> tuple[str, ...]:
        if recommendation is None or recommendation.status != "SUCCESS":
            return ()

        values: list[str] = []
        for item in recommendation.candidates:
            value = item.brand if next_field == "brand" else item.model
            if value and value not in values:
                values.append(value)
            if len(values) == 3:
                break

        return tuple(values)

    @staticmethod
    def _recommendation_source_label(
        recommendation: RecommendProductOptionsResult | None,
    ) -> str:
        if recommendation is None:
            return "系统推荐"

        # Do not infer “采购白名单” merely because the missing field is brand.
        # The current candidate schema can expose purchase-history provenance;
        # otherwise use a neutral label until the backend explicitly provides
        # a whitelist/source field.
        sources = {item.source for item in recommendation.candidates}
        if sources == {"PURCHASE_HISTORY"}:
            return "历史采购记录"
        return "系统推荐"

    async def _history_card_response(
        self,
        *,
        result: QueryPurchaseRequestsResult,
        context: AssistantToolContext,
        external_message_id: str,
        narrative: str | None = None,
    ) -> AssistantResponse:
        total = result.total_count or 0
        text = (
            narrative
            or f"已查询到您可见的采购申请共 {total} 条。点击下方单据可查看具体需求和当前状态。"
        )
        await self._append_reply(context, external_message_id, text)

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
