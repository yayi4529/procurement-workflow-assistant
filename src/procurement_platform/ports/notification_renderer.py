from typing import Protocol

from procurement_platform.domain.notification import (
    NotificationContent,
    NotificationGatewayRequest,
)


class NotificationRenderer(Protocol):
    event_type: str

    def render(self, request: NotificationGatewayRequest) -> NotificationContent: ...
