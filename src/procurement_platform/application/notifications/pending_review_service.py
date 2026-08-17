# ruff: noqa: RUF001

from procurement_platform.application.card_values import quantity_text
from procurement_platform.application.notifications.workflow_assignment_renderer import (
    WorkflowAssignmentPayload,
)
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import ActionButton, InteractionView, MarkdownBlock
from procurement_platform.domain.notification import (
    InteractionNotification,
    NotificationGatewayRequest,
)
from procurement_platform.ports.backend_client import BackendClient


class PendingReviewNotificationService:
    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def render(self, request: NotificationGatewayRequest) -> InteractionNotification:
        payload = WorkflowAssignmentPayload.model_validate(request.payload)
        identity = PlatformIdentity.create(PlatformType.FEISHU, request.receiver_platform_user_id)
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=payload.requirement_id
        )
        timeline = await self._backend.get_requirement_timeline(
            identity=identity, requirement_id=payload.requirement_id
        )
        applicant = next(
            (item for item in timeline.items if item.operator_role_name in {"需求人", "APPLICANT"}),
            timeline.items[0] if timeline.items else None,
        )
        applicant_contact = (
            await self._backend.get_timeline_contact(
                identity=identity,
                requirement_id=payload.requirement_id,
                log_id=applicant.log_id,
                subject="operator",
            )
            if applicant
            else None
        )
        fields = detail.applicant_fields
        application_date = (
            applicant.operated_at.astimezone().date().isoformat() if applicant else "-"
        )
        markdown = (
            "有一条采购申请等待您审核，请查看详情。\n\n"
            f"**采购单编号：** {detail.requirement_no}\n"
            f"**申请人：** {applicant.operator_name if applicant else '-'}\n"
            f"**申请人联系方式：** {applicant_contact.mobile if applicant_contact else '-'}\n"
            f"**申请时间：** {application_date}\n"
            f"**所属楼宇：** {detail.building.building_name}\n"
            f"**设备名称：** {fields.device_name or '-'}\n"
            f"**品牌/型号：** {fields.brand or '-'} / {fields.model or '-'}\n"
            f"**数量：** {quantity_text(fields.quantity)} {fields.unit or ''}\n"
            f"**需求原因：** {fields.application_reason or '-'}"
        )
        return InteractionNotification(
            view=InteractionView(
                title="楼长待审核采购申请",
                elements=(MarkdownBlock(markdown=markdown),),
                actions=(
                    ActionButton(
                        action_id="building_manager.open_requirement",
                        label="打开审核卡片",
                        value={"requirement_id": detail.requirement_id},
                        style="primary",
                    ),
                ),
            )
        )
