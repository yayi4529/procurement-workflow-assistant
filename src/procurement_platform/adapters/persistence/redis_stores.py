import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from secrets import token_urlsafe
from typing import Protocol

from procurement_platform.ports.event_dedup_store import EventStartResult
from procurement_platform.ports.notification_delivery_store import NotificationStartResult


class RedisClient(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object: ...


_EVENT_START = """
local state = redis.call('GET', KEYS[1])
if not state then redis.call('SET', KEYS[1], 'started', 'EX', ARGV[1]); return 'STARTED' end
if state == 'completed' then return 'ALREADY_COMPLETED' end
if state == 'started' then return 'IN_PROGRESS' end
redis.call('SET', KEYS[1], 'started', 'EX', ARGV[1]); return 'RETRY_ALLOWED'
"""

_LOCK_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""

_DELIVERY_START = """
local current = redis.call('HMGET', KEYS[1], 'notification_id', 'fingerprint', 'state')
if not current[1] then
  redis.call('HSET', KEYS[1], 'notification_id', ARGV[1], 'fingerprint', ARGV[2])
  redis.call('HSET', KEYS[1], 'state', 'started', 'attempt_count', 1)
  redis.call('EXPIRE', KEYS[1], ARGV[3]); return 'STARTED'
end
if current[1] ~= ARGV[1] or current[2] ~= ARGV[2] then return 'CONFLICT' end
if current[3] == 'succeeded' then return 'ALREADY_SUCCEEDED' end
if current[3] == 'started' then return 'IN_PROGRESS' end
redis.call('HSET', KEYS[1], 'state', 'started')
redis.call('HINCRBY', KEYS[1], 'attempt_count', 1)
redis.call('EXPIRE', KEYS[1], ARGV[3]); return 'RETRY_ALLOWED'
"""


def _text(value: object) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _integer(value: object) -> int:
    return int(_text(value))


class RedisEventDedupStore:
    def __init__(self, client: RedisClient, *, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(event_id: str) -> str:
        return f"feishu:event:{event_id}"

    async def try_start(self, *, event_id: str) -> EventStartResult:
        result = await self._client.eval(_EVENT_START, 1, self._key(event_id), self._ttl_seconds)
        return EventStartResult(_text(result))

    async def mark_completed(self, *, event_id: str) -> None:
        await self._set_state(event_id, "completed")

    async def mark_failed(self, *, event_id: str) -> None:
        await self._set_state(event_id, "failed")

    async def _set_state(self, event_id: str, state: str) -> None:
        await self._client.eval(
            "redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2]); return 1",
            1,
            self._key(event_id),
            state,
            self._ttl_seconds,
        )


class RedisConversationLockManager:
    def __init__(
        self,
        client: RedisClient,
        *,
        lease_seconds: int,
        acquire_timeout_seconds: float,
    ) -> None:
        self._client = client
        self._lease_seconds = lease_seconds
        self._acquire_timeout_seconds = acquire_timeout_seconds

    @asynccontextmanager
    async def acquire(self, *, key: str) -> AsyncIterator[None]:
        redis_key = f"conversation:{key}"
        owner = token_urlsafe(24)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._acquire_timeout_seconds
        while True:
            claimed = await self._client.eval(
                "if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[2]) "
                "then return 1 else return 0 end",
                1,
                redis_key,
                owner,
                self._lease_seconds,
            )
            if _integer(claimed) == 1:
                break
            if loop.time() >= deadline:
                raise TimeoutError("conversation lock acquisition timed out")
            await asyncio.sleep(0.05)
        try:
            yield
        finally:
            await self._client.eval(_LOCK_RELEASE, 1, redis_key, owner)


class RedisNotificationDeliveryStore:
    def __init__(self, client: RedisClient, *, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(dedup_key: str) -> str:
        return f"notification:delivery:{dedup_key}"

    async def try_start(
        self, *, dedup_key: str, notification_id: int, payload_fingerprint: str
    ) -> NotificationStartResult:
        result = await self._client.eval(
            _DELIVERY_START,
            1,
            self._key(dedup_key),
            notification_id,
            payload_fingerprint,
            self._ttl_seconds,
        )
        return NotificationStartResult(_text(result))

    async def mark_succeeded(self, *, dedup_key: str, external_message_id: str | None) -> None:
        await self._mark(dedup_key, "succeeded", "external_message_id", external_message_id or "")

    async def mark_failed(self, *, dedup_key: str, error_code: str) -> None:
        await self._mark(dedup_key, "failed", "last_error", error_code)

    async def _mark(self, dedup_key: str, state: str, field: str, value: str) -> None:
        await self._client.eval(
            "redis.call('HSET', KEYS[1], 'state', ARGV[1], ARGV[2], ARGV[3]); "
            "redis.call('EXPIRE', KEYS[1], ARGV[4]); return 1",
            1,
            self._key(dedup_key),
            state,
            field,
            value,
            self._ttl_seconds,
        )
