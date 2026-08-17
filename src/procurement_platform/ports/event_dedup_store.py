from enum import StrEnum
from typing import Protocol


class EventStartResult(StrEnum):
    STARTED = "STARTED"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    IN_PROGRESS = "IN_PROGRESS"
    RETRY_ALLOWED = "RETRY_ALLOWED"


class EventDedupStore(Protocol):
    async def try_start(self, *, event_id: str) -> EventStartResult: ...
    async def mark_completed(self, *, event_id: str) -> None: ...
    async def mark_failed(self, *, event_id: str) -> None: ...
