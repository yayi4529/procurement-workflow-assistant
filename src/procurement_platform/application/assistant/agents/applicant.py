"""Thin applicant role boundary for the agentic assistant runtime."""

# ruff: noqa: RUF001

from procurement_platform.application.applicant.card_factory import ApplicantCardFactory
from procurement_platform.application.assistant.agents.base import BasicRoleAgent
from procurement_platform.application.assistant.prompts.applicant import APPLICANT_PROMPT
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tooling import (
    QueryPurchaseRequestsResult,
    RecommendProductOptionsResult,
    UpdatePurchaseDraftResult,
)
from procurement_platform.application.assistant.tools import ToolExecutor
from procurement_platform.application.status_labels import requirement_status_label
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import ActionButton, InteractionView, MarkdownBlock
from procurement_platform.ports.backend_client import BackendClient
from procurement_platform.ports.llm_client import LlmClient


class ApplicantAgent(BasicRoleAgent):
    """Lets the LLM understand intent while tools enforce procurement truth."""

    role = RoleCode.APPLICANT
    role_prompt = APPLICANT_PROMPT
    tool_names = frozenset(
        {"query_purchase_requests", "recommend_product_options", "update_purchase_draft"}
    )

    def __init__(
        self,
        *,
        backend_client: BackendClient,
        llm_client: LlmClient,
        session_service: AssistantSessionService,
        tool_executor: ToolExecutor,
    ) -> None:
        del llm_client, tool_executor
        super().__init__(session_service)
        self._backend_client = backend_client

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if isinstance(result, RecommendProductOptionsResult):
            if result.status in {"NOT_FOUND", "NEED_MORE_INFORMATION", "SUCCESS"}:
                # Absence of recommendations is a normal business observation,
                # not a safety failure. Let the LLM ask for the missing value.
                return None

        if isinstance(result, UpdatePurchaseDraftResult):
            if result.status != "SUCCESS":
                return await super().handle_tool_result(
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
            return None

        if isinstance(result, QueryPurchaseRequestsResult):
            if result.status == "NOT_FOUND" and result.total_count == 0:
                return await self._history_card_response(
                    result=result,
                    context=context,
                    external_message_id=external_message_id,
                )
            if result.status not in {"SUCCESS", "MULTIPLE_MATCHES"}:
                return await super().handle_tool_result(
                    result=result,
                    context=context,
                    external_message_id=external_message_id,
                )
            if result.total_count is not None:
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

    async def _completed_draft_response(
        self,
        *,
        result: UpdatePurchaseDraftResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse:
        assert result.requirement_id is not None
        detail = await self._backend_client.get_requirement(
            identity=self._identity(context), requirement_id=result.requirement_id
        )
        notice = "草稿已保存到采购后端，字段已完整。请在正式需求卡片中确认并提交。"
        await self._append_reply(context, external_message_id, notice)
        return AssistantInteractionResponse(
            view=ApplicantCardFactory().detail(detail, notice=notice)
        )

    async def _history_card_response(
        self,
        *,
        result: QueryPurchaseRequestsResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse:
        total = result.total_count if result.total_count is not None else len(result.records)
        text = f"已查询到您可见的采购申请共 {total} 条。"
        await self._append_reply(context, external_message_id, text)
        lines = [text, "", f"共 **{total}** 条采购申请"]
        actions: list[ActionButton] = []
        return_ids = [item.requirement_id for item in result.records]
        for item in result.records:
            lines.append(
                f"- {item.requirement_no} | {item.device_name or '未填写'} | "
                f"{requirement_status_label(item.status)}"
            )
            actions.append(
                ActionButton(
                    action_id="applicant.open",
                    label=f"查看 {item.requirement_no}",
                    value={
                        "requirement_id": item.requirement_id,
                        "return_requirement_ids": return_ids,
                    },
                )
            )
        if total > len(result.records):
            lines.append(f"当前展示前 {len(result.records)} 条")
        return AssistantInteractionResponse(
            view=InteractionView(
                title="我的采购申请",
                subtitle="实时查询结果",
                elements=(MarkdownBlock(markdown="\n".join(lines)),),
                actions=tuple(actions),
            )
        )

    @staticmethod
    def _identity(context: AssistantToolContext) -> PlatformIdentity:
        return PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
