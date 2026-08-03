import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class LocalConversationLockManager:
    """Per-process lock manager; idle locks are removed after their holder exits."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, *, key: str) -> AsyncIterator[None]:
        async with self._guard:
            lock = self._locks.setdefault(key, asyncio.Lock())
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
            async with self._guard:
                if not lock.locked() and self._locks.get(key) is lock:
                    self._locks.pop(key, None)
