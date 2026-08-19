# ruff: noqa: RUF001

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from procurement_platform.application.status_labels import requirement_status_label
from procurement_platform.domain.enums import RequirementStatus
from procurement_platform.domain.interaction import ActionButton, InteractionView, MarkdownBlock
from procurement_platform.domain.notification import (
    InteractionNotification,
    NotificationGatewayRequest,
)


class WorkflowAssignmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: int
    requirement_no: str
    status: str
    item_count: int | None = None
    item_summary: str | None = None


class WorkflowAssignmentRenderer:
    event_type: str
    _metadata: ClassVar[dict[str, tuple[str, str, str, str]]] = {
        "REQUIREMENT_PENDING_REVIEW": (
            "楼长待审核采购申请",
            "有一条采购申请等待您审核。",
            "打开审核卡片",
            "building_manager.open_requirement",
        ),
        "REQUIREMENT_PENDING_PURCHASE": (
            "采购员待采购申请",
            "有一条采购申请等待您开始采购。",
            "打开采购卡片",
            "purchaser.open_requirement",
        ),
        "REQUIREMENT_PENDING_WAREHOUSE": (
            "仓库待入库采购申请",
            "有一条采购申请等待您登记入库。",
            "打开入库卡片",
            "warehouse.open_requirement",
        ),
    }

    def __init__(self, event_type: str) -> None:
        if event_type not in self._metadata:
            raise ValueError(f"unsupported workflow assignment event: {event_type}")
        self.event_type = event_type

    def render(self, request: NotificationGatewayRequest) -> InteractionNotification:
        payload = WorkflowAssignmentPayload.model_validate(request.payload)
        try:
            status = requirement_status_label(RequirementStatus(payload.status))
        except ValueError:
            status = payload.status
        title, message, button_label, action_id = self._metadata[self.event_type]
        item_line = ""
        if payload.item_summary:
            count = f"（共 {payload.item_count} 项）" if payload.item_count else ""
            item_line = f"\n**采购项:** {payload.item_summary}{count}"
        return InteractionNotification(
            view=InteractionView(
                title=title,
                elements=(
                    MarkdownBlock(
                        markdown=(
                            f"{message}\n\n"
                            f"**采购单编号:** {payload.requirement_no}\n"
                            f"**当前状态:** {status}{item_line}"
                        )
                    ),
                ),
                actions=(
                    ActionButton(
                        action_id=action_id,
                        label=button_label,
                        value={"requirement_id": payload.requirement_id},
                        style="primary",
                    ),
                ),
            )
        )
