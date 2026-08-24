"""Compatibility presentation migrated from the former role-specific text agents.

This presenter is intentionally deterministic and can be removed after presentation contracts
are redesigned in a later task. It never performs a formal procurement transition.
"""

# ruff: noqa: RUF001

from procurement_platform.application.applicant.card_factory import ApplicantCardFactory
from procurement_platform.application.assistant.capabilities.products.recommend import (
    RecommendProductsByNameResult,
)
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tooling import (
    FillSelectedSupplierProfileResult,
    PreparePurchasePrefillResult,
    QueryPurchaseRequestsResult,
    RecommendProductOptionsResult,
    UpdatePurchaseDraftResult,
    UpdatePurchaseExecutionDraftResult,
    UpdateReviewDraftResult,
    UpdateWarehouseReceiptDraftResult,
)
from procurement_platform.application.assistant.tooling.multi_item import (
    UpdateMultiItemDraftResult,
)
from procurement_platform.application.building_manager.card_factory import (
    BuildingManagerCardFactory,
)
from procurement_platform.application.purchaser.card_factory import PurchaserCardFactory
from procurement_platform.application.status_labels import requirement_status_label
from procurement_platform.application.warehouse.card_factory import WarehouseCardFactory
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.enums import AgentMessageSender, PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import ActionButton, InteractionView, MarkdownBlock
from procurement_platform.ports.backend_client import BackendClient


class LegacyToolResultPresenter:
    def __init__(
        self,
        *,
        backend_client: BackendClient,
        session_service: AssistantSessionService,
    ) -> None:
        self._backend_client = backend_client
        self._session_service = session_service

    async def present(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if result.exact_render_required and result.user_message:
            return await self._text_response(context, external_message_id, result.user_message)
        if isinstance(result, RecommendProductsByNameResult) and result.status == "SUCCESS":
            assert result.response is not None
            lines = [
                "查询到该物品之前的采购历史。请选择下列品牌或型号的序号，"
                "或直接输入您想购买的品牌和型号：",
                "",
            ]
            for index, item in enumerate(result.response.items, start=1):
                label = item.brand or "未记录品牌"
                if item.model:
                    label += f"（型号：{item.model}）"
                if item.last_purchased_at is not None:
                    label += f" — 最近采购于 {item.last_purchased_at.date().isoformat()}"
                # Feishu Markdown may restart separately rendered ordered-list blocks at 1.
                # A Chinese enumeration delimiter preserves the intended visible numbering.
                lines.append(f"{index}、{label}")
            return await self._text_response(context, external_message_id, "\n".join(lines))
        if isinstance(result, QueryPurchaseRequestsResult) and result.status == "SUCCESS":
            return await self._history_card(result, context, external_message_id)
        if isinstance(result, RecommendProductOptionsResult) and result.status in {
            "NOT_FOUND",
            "NEED_MORE_INFORMATION",
            "SUCCESS",
        }:
            return None
        if isinstance(result, (PreparePurchasePrefillResult, FillSelectedSupplierProfileResult)):
            if result.status in {"SUCCESS", "NEED_MORE_INFORMATION"}:
                return None
        if isinstance(result, UpdatePurchaseDraftResult):
            if result.status == "SUCCESS" and result.fields_complete:
                return await self._applicant_card(result, context, external_message_id)
            return None
        if isinstance(result, UpdateMultiItemDraftResult):
            if (
                result.status == "SUCCESS"
                and result.fields_complete
                and result.requirement_id is not None
            ):
                return await self._multi_item_applicant_card(result, context, external_message_id)
            return None
        if isinstance(result, UpdateReviewDraftResult):
            if result.status == "SUCCESS" and result.fields_complete:
                return await self._review_card(result, context, external_message_id)
            return None
        if isinstance(result, UpdatePurchaseExecutionDraftResult):
            if result.status == "SUCCESS" and result.fields_complete:
                return await self._purchase_card(result, context, external_message_id)
            return None
        if isinstance(result, UpdateWarehouseReceiptDraftResult):
            if result.status == "SUCCESS" and result.fields_complete:
                return await self._warehouse_card(result, context, external_message_id)
            return None
        # Read observations return to the LLM so it can continue planning and synthesize a
        # response. Only completed drafts and exact-render safety responses terminate a turn.
        return None

    async def _applicant_card(
        self,
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

    async def _review_card(
        self,
        result: UpdateReviewDraftResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        requirement_id = result.requirement_id or context.active_requirement_id
        if requirement_id is None:
            return None
        detail = await self._backend_client.get_requirement(
            identity=self._identity(context), requirement_id=requirement_id
        )
        notice = "审核信息已完整，请在正式审核卡片中确认后执行审批、驳回或提交采购员。"
        await self._append_reply(context, external_message_id, notice)
        return AssistantInteractionResponse(
            view=BuildingManagerCardFactory().detail(detail, notice=notice)
        )

    async def _multi_item_applicant_card(
        self,
        result: UpdateMultiItemDraftResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse:
        assert result.requirement_id is not None
        detail = await self._backend_client.get_requirement(
            identity=self._identity(context), requirement_id=result.requirement_id
        )
        notice = "多采购项草稿已完整，请在正式确认卡中检查并提交。"
        await self._append_reply(context, external_message_id, notice)
        return AssistantInteractionResponse(
            view=ApplicantCardFactory().detail(detail, notice=notice)
        )

    async def _purchase_card(
        self,
        result: UpdatePurchaseExecutionDraftResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse:
        assert result.requirement_id is not None
        detail = await self._backend_client.get_requirement(
            identity=self._identity(context), requirement_id=result.requirement_id
        )
        notice = "采购执行草稿已完整, 请在正式采购卡片中审核并执行后续操作。"
        await self._append_reply(context, external_message_id, notice)
        return AssistantInteractionResponse(
            view=PurchaserCardFactory().detail(detail, notice=notice)
        )

    async def _warehouse_card(
        self,
        result: UpdateWarehouseReceiptDraftResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse:
        assert result.requirement_id is not None
        detail = await self._backend_client.get_requirement(
            identity=self._identity(context), requirement_id=result.requirement_id
        )
        notice = "入库草稿已完整，请在正式仓库卡片中确认后完成入库。"
        await self._append_reply(context, external_message_id, notice)
        return AssistantInteractionResponse(
            view=WarehouseCardFactory().detail(detail, notice=notice)
        )

    async def _history_card(
        self,
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

    async def _text_response(
        self,
        context: AssistantToolContext,
        external_message_id: str,
        text: str,
    ) -> AssistantTextResponse:
        await self._append_reply(context, external_message_id, text)
        return AssistantTextResponse(text=text)

    async def _append_reply(
        self, context: AssistantToolContext, external_message_id: str, text: str
    ) -> None:
        await self._session_service.append(
            identity=self._identity(context),
            conversation_id=context.conversation_id,
            external_message_id=f"assistant:{external_message_id}",
            sender=AgentMessageSender.AGENT,
            content=text,
        )

    @staticmethod
    def _identity(context: AssistantToolContext) -> PlatformIdentity:
        return PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )

    @staticmethod
    def _is_applicant_only(context: AssistantToolContext) -> bool:
        return {item.role_code for item in context.current_user.roles} == {RoleCode.APPLICANT}
