import hashlib
import hmac
import json

from pydantic import ValidationError

from procurement_platform.application.notifications.renderer_registry import (
    NotificationRendererRegistry,
)
from procurement_platform.domain.channel import ChannelRecipient, ChannelType
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.errors import (
    NotificationAuthenticationError,
    NotificationHeaderMismatchError,
    NotificationIdempotencyConflictError,
    NotificationInProgressError,
    NotificationPayloadValidationError,
)
from procurement_platform.domain.notification import (
    InteractionNotification,
    NotificationGatewayRequest,
    TextNotification,
)
from procurement_platform.ports.channel import ChannelClient
from procurement_platform.ports.notification_delivery_store import (
    NotificationDeliveryStore,
    NotificationStartResult,
)


class NotificationGatewayService:
    def __init__(
        self,
        *,
        channel_client: ChannelClient,
        delivery_store: NotificationDeliveryStore,
        renderer_registry: NotificationRendererRegistry,
        bearer_token: str | None,
    ) -> None:
        self._channel = channel_client
        self._store = delivery_store
        self._registry = renderer_registry
        self._bearer_token = bearer_token

    async def deliver(
        self,
        *,
        request: NotificationGatewayRequest,
        authorization: str | None,
        idempotency_key: str | None,
        notification_id_header: str | None,
    ) -> None:
        self._authenticate(authorization)
        if idempotency_key != request.dedup_key:
            raise NotificationHeaderMismatchError("Idempotency-Key does not match body")
        if notification_id_header != str(request.notification_id):
            raise NotificationHeaderMismatchError("X-Notification-Id does not match body")
        if request.platform_type != PlatformType.FEISHU:
            raise NotificationPayloadValidationError("only FEISHU is supported")

        fingerprint = hashlib.sha256(
            json.dumps(
                request.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        start = await self._store.try_start(
            dedup_key=request.dedup_key,
            notification_id=request.notification_id,
            payload_fingerprint=fingerprint,
        )
        if start == NotificationStartResult.ALREADY_SUCCEEDED:
            return
        if start == NotificationStartResult.CONFLICT:
            raise NotificationIdempotencyConflictError("idempotency key conflict")
        if start == NotificationStartResult.IN_PROGRESS:
            raise NotificationInProgressError("notification delivery is in progress")

        try:
            content = self._registry.resolve(request.event_type).render(request)
            recipient = ChannelRecipient(
                channel=ChannelType.FEISHU,
                platform_user_id=request.receiver_platform_user_id,
            )
            if isinstance(content, TextNotification):
                result = await self._channel.send_text(recipient=recipient, text=content.text)
            elif isinstance(content, InteractionNotification):
                result = await self._channel.send_interaction(
                    recipient=recipient, view=content.view
                )
            else:
                raise NotificationPayloadValidationError("unsupported rendered content")
            if not result.delivered:
                raise RuntimeError("channel reported unsuccessful delivery")
        except ValidationError as exc:
            await self._store.mark_failed(
                dedup_key=request.dedup_key, error_code="PAYLOAD_VALIDATION"
            )
            raise NotificationPayloadValidationError("notification payload is invalid") from exc
        except Exception as exc:
            await self._store.mark_failed(
                dedup_key=request.dedup_key, error_code=type(exc).__name__
            )
            raise
        await self._store.mark_succeeded(
            dedup_key=request.dedup_key,
            external_message_id=result.external_message_id,
        )

    def _authenticate(self, authorization: str | None) -> None:
        if self._bearer_token is None:
            return
        expected = f"Bearer {self._bearer_token}"
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise NotificationAuthenticationError("invalid notification bearer token")
