import asyncio

from procurement_platform.ports.event_dedup_store import EventStartResult


class MemoryEventDedupStore:
    def __init__(self) -> None:
        self._states: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def try_start(self, *, event_id: str) -> EventStartResult:
        async with self._lock:
            state = self._states.get(event_id)
            if state == "completed":
                return EventStartResult.ALREADY_COMPLETED
            if state == "started":
                return EventStartResult.IN_PROGRESS
            result = (
                EventStartResult.RETRY_ALLOWED if state == "failed" else EventStartResult.STARTED
            )
            self._states[event_id] = "started"
            return result

    async def mark_completed(self, *, event_id: str) -> None:
        async with self._lock:
            self._states[event_id] = "completed"

    async def mark_failed(self, *, event_id: str) -> None:
        async with self._lock:
            self._states[event_id] = "failed"
