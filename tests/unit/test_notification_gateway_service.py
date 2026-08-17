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
from procurement_platform.domain.interaction import InteractionView
from procurement_platform.domain.notification import (
    InteractionNotification,
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


class PendingPurchaseRenderer:
    event_type = "REQUIREMENT_PENDING_PURCHASE"

    def render(self, request: NotificationGatewayRequest) -> TextNotification:
        return TextNotification(text="ordinary notification")


class SuccessfulPrefillProvider:
    async def render(self, request: NotificationGatewayRequest) -> InteractionNotification | None:
        return InteractionNotification(view=InteractionView(title="prefill", elements=()))


class FailingPrefillProvider:
    async def render(self, request: NotificationGatewayRequest) -> InteractionNotification | None:
        raise RuntimeError("backend unavailable")


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected_interactions", "expected_texts"),
    [
        (SuccessfulPrefillProvider(), 1, 0),
        (FailingPrefillProvider(), 0, 1),
    ],
)
async def test_pending_purchase_prefill_succeeds_or_falls_back(
    provider: SuccessfulPrefillProvider | FailingPrefillProvider,
    expected_interactions: int,
    expected_texts: int,
) -> None:
    fake = FakeFeishuClient()
    registry = NotificationRendererRegistry()
    registry.register(PendingPurchaseRenderer())
    service = NotificationGatewayService(
        channel_client=fake,
        delivery_store=MemoryNotificationDeliveryStore(),
        renderer_registry=registry,
        bearer_token=None,
        purchase_prefill_provider=provider,
    )
    pending = NotificationGatewayRequest(
        notification_id=2,
        dedup_key="pending-purchase",
        event_type="REQUIREMENT_PENDING_PURCHASE",
        platform_type=PlatformType.FEISHU,
        receiver_platform_user_id="ou_purchaser",
        payload={"requirement_id": 42},
    )

    await service.deliver(
        request=pending,
        authorization=None,
        idempotency_key="pending-purchase",
        notification_id_header="2",
    )

    assert len(fake.send_interaction_calls) == expected_interactions
    assert len(fake.send_text_calls) == expected_texts
