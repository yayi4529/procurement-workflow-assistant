from enum import StrEnum
from typing import Protocol


class NotificationStartResult(StrEnum):
    STARTED = "STARTED"
    ALREADY_SUCCEEDED = "ALREADY_SUCCEEDED"
    IN_PROGRESS = "IN_PROGRESS"
    CONFLICT = "CONFLICT"
    RETRY_ALLOWED = "RETRY_ALLOWED"


class NotificationDeliveryStore(Protocol):
    async def try_start(
        self, *, dedup_key: str, notification_id: int, payload_fingerprint: str
    ) -> NotificationStartResult: ...
    async def mark_succeeded(self, *, dedup_key: str, external_message_id: str | None) -> None: ...
    async def mark_failed(self, *, dedup_key: str, error_code: str) -> None: ...
