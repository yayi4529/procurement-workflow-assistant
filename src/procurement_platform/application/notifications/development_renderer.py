from pydantic import BaseModel, ConfigDict

from procurement_platform.domain.interaction import InteractionView, MarkdownBlock
from procurement_platform.domain.notification import (
    InteractionNotification,
    NotificationGatewayRequest,
)


class DevelopmentNotificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: int
    requirement_no: str
    title: str
    message: str | None = None


class DevelopmentNotificationRenderer:
    event_type = "DEV_NOTIFICATION_TEST"

    def render(self, request: NotificationGatewayRequest) -> InteractionNotification:
        payload = DevelopmentNotificationPayload.model_validate(request.payload)
        detail = (
            f"**采购单:** {payload.requirement_no}\n"
            f"**ID:** {payload.requirement_id}\n"
            f"**标题:** {payload.title}"
        )
        if payload.message:
            detail += f"\n**说明:** {payload.message}"
        return InteractionNotification(
            view=InteractionView(
                title="【测试环境】通知网关 Smoke Test",
                subtitle="此卡片不是正式采购通知",
                elements=(MarkdownBlock(markdown=detail),),
            )
        )
