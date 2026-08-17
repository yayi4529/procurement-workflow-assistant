from collections import deque

import pytest

from procurement_platform.adapters.persistence.redis_stores import (
    RedisConversationLockManager,
    RedisEventDedupStore,
    RedisNotificationDeliveryStore,
)
from procurement_platform.ports.event_dedup_store import EventStartResult
from procurement_platform.ports.notification_delivery_store import NotificationStartResult


class ScriptedRedis:
    def __init__(self, *results: object) -> None:
        self.results = deque(results)
        self.calls: list[tuple[str, int, tuple[object, ...]]] = []

    async def eval(self, script: str, numkeys: int, *args: object) -> object:
        self.calls.append((script, numkeys, args))
        return self.results.popleft() if self.results else 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("STARTED", EventStartResult.STARTED),
        (b"ALREADY_COMPLETED", EventStartResult.ALREADY_COMPLETED),
        ("IN_PROGRESS", EventStartResult.IN_PROGRESS),
        ("RETRY_ALLOWED", EventStartResult.RETRY_ALLOWED),
    ],
)
async def test_redis_event_claim_maps_atomic_script_result(
    raw: object, expected: EventStartResult
) -> None:
    client = ScriptedRedis(raw)
    store = RedisEventDedupStore(client, ttl_seconds=123)

    assert await store.try_start(event_id="event-1") is expected
    assert client.calls[0][2] == ("feishu:event:event-1", 123)


async def test_redis_lock_releases_only_with_its_owner_token() -> None:
    client = ScriptedRedis(1, 1)
    lock = RedisConversationLockManager(client, lease_seconds=30, acquire_timeout_seconds=1)

    async with lock.acquire(key="conversation-7"):
        pass

    assert client.calls[0][2][0] == "conversation:conversation-7"
    assert client.calls[1][2] == ("conversation:conversation-7", client.calls[0][2][1])
    assert "DEL" in client.calls[1][0]


async def test_redis_delivery_claim_preserves_business_fingerprint() -> None:
    client = ScriptedRedis("STARTED", "CONFLICT")
    store = RedisNotificationDeliveryStore(client, ttl_seconds=456)

    assert (
        await store.try_start(
            dedup_key="action:recipient:type",
            notification_id=9,
            payload_fingerprint="sha256",
        )
        is NotificationStartResult.STARTED
    )
    assert (
        await store.try_start(
            dedup_key="action:recipient:type",
            notification_id=10,
            payload_fingerprint="other",
        )
        is NotificationStartResult.CONFLICT
    )
    assert client.calls[0][2] == (
        "notification:delivery:action:recipient:type",
        9,
        "sha256",
        456,
    )
