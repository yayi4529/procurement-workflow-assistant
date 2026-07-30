import pytest

from procurement_platform.adapters.feishu.fake_client import FakeFeishuClient
from procurement_platform.adapters.persistence.memory_notification_delivery_store import (
    MemoryNotificationDeliveryStore,
)
from procurement_platform.application.notifications.gateway_service import (
    NotificationGatewayService,
)
from procurement_platform.application.notifications.renderer_registry import (
    NotificationRendererRegistry,
)
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.errors import (
    NotificationAuthenticationError,
    NotificationIdempotencyConflictError,
)
from procurement_platform.domain.notification import (
    NotificationGatewayRequest,
    TextNotification,
)


class TestRenderer:
    event_type = "test.only"

    def render(self, request: NotificationGatewayRequest) -> TextNotification:
        text = request.payload.get("text")
        if not isinstance(text, str):
            raise ValueError("text required")
        return TextNotification(text=text)


def request(text: str = "hello") -> NotificationGatewayRequest:
    return NotificationGatewayRequest(
        notification_id=1,
        dedup_key="dedup",
        event_type="test.only",
        platform_type=PlatformType.FEISHU,
        receiver_platform_user_id="ou_user",
        payload={"text": text},
    )


@pytest.mark.asyncio
async def test_gateway_authenticates_and_delivers_once() -> None:
    fake = FakeFeishuClient()
    registry = NotificationRendererRegistry()
    registry.register(TestRenderer())
    service = NotificationGatewayService(
        channel_client=fake,
        delivery_store=MemoryNotificationDeliveryStore(),
        renderer_registry=registry,
        bearer_token="token",
    )
    await service.deliver(
        request=request(),
        authorization="Bearer token",
        idempotency_key="dedup",
        notification_id_header="1",
    )
    await service.deliver(
        request=request(),
        authorization="Bearer token",
        idempotency_key="dedup",
        notification_id_header="1",
    )
    assert len(fake.send_text_calls) == 1
    with pytest.raises(NotificationAuthenticationError):
        await service.deliver(
            request=request(),
            authorization=None,
            idempotency_key="dedup",
            notification_id_header="1",
        )


@pytest.mark.asyncio
async def test_gateway_detects_changed_payload() -> None:
    registry = NotificationRendererRegistry()
    registry.register(TestRenderer())
    service = NotificationGatewayService(
        channel_client=FakeFeishuClient(),
        delivery_store=MemoryNotificationDeliveryStore(),
        renderer_registry=registry,
        bearer_token=None,
    )
    await service.deliver(
        request=request(),
        authorization=None,
        idempotency_key="dedup",
        notification_id_header="1",
    )
    with pytest.raises(NotificationIdempotencyConflictError):
        await service.deliver(
            request=request("changed"),
            authorization=None,
            idempotency_key="dedup",
            notification_id_header="1",
        )
