import asyncio
from dataclasses import dataclass

from procurement_platform.ports.notification_delivery_store import NotificationStartResult


@dataclass(slots=True)
class _Delivery:
    notification_id: int
    payload_fingerprint: str
    state: str
    external_message_id: str | None = None
    error_code: str | None = None


class MemoryNotificationDeliveryStore:
    def __init__(self) -> None:
        self._deliveries: dict[str, _Delivery] = {}
        self._lock = asyncio.Lock()

    async def try_start(
        self, *, dedup_key: str, notification_id: int, payload_fingerprint: str
    ) -> NotificationStartResult:
        async with self._lock:
            delivery = self._deliveries.get(dedup_key)
            if delivery is None:
                self._deliveries[dedup_key] = _Delivery(
                    notification_id, payload_fingerprint, "started"
                )
                return NotificationStartResult.STARTED
            if (
                delivery.notification_id != notification_id
                or delivery.payload_fingerprint != payload_fingerprint
            ):
                return NotificationStartResult.CONFLICT
            if delivery.state == "succeeded":
                return NotificationStartResult.ALREADY_SUCCEEDED
            if delivery.state == "started":
                return NotificationStartResult.IN_PROGRESS
            delivery.state = "started"
            return NotificationStartResult.RETRY_ALLOWED

    async def mark_succeeded(self, *, dedup_key: str, external_message_id: str | None) -> None:
        async with self._lock:
            delivery = self._deliveries[dedup_key]
            delivery.state = "succeeded"
            delivery.external_message_id = external_message_id

    async def mark_failed(self, *, dedup_key: str, error_code: str) -> None:
        async with self._lock:
            delivery = self._deliveries[dedup_key]
            delivery.state = "failed"
            delivery.error_code = error_code

    async def get_external_message_id(self, dedup_key: str) -> str | None:
        async with self._lock:
            delivery = self._deliveries.get(dedup_key)
            return None if delivery is None else delivery.external_message_id
