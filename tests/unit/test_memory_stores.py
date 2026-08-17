import asyncio

import pytest

from procurement_platform.adapters.persistence.memory_event_dedup_store import (
    MemoryEventDedupStore,
)
from procurement_platform.adapters.persistence.memory_notification_delivery_store import (
    MemoryNotificationDeliveryStore,
)
from procurement_platform.ports.event_dedup_store import EventStartResult
from procurement_platform.ports.notification_delivery_store import NotificationStartResult


@pytest.mark.asyncio
async def test_event_store_retry_and_concurrency() -> None:
    store = MemoryEventDedupStore()
    results = await asyncio.gather(
        store.try_start(event_id="e"),
        store.try_start(event_id="e"),
    )
    assert set(results) == {EventStartResult.STARTED, EventStartResult.IN_PROGRESS}
    await store.mark_failed(event_id="e")
    assert await store.try_start(event_id="e") == EventStartResult.RETRY_ALLOWED
    await store.mark_completed(event_id="e")
    assert await store.try_start(event_id="e") == EventStartResult.ALREADY_COMPLETED


@pytest.mark.asyncio
async def test_notification_store_conflict_success_and_retry() -> None:
    store = MemoryNotificationDeliveryStore()
    assert (
        await store.try_start(dedup_key="k", notification_id=1, payload_fingerprint="a")
        == NotificationStartResult.STARTED
    )
    assert (
        await store.try_start(dedup_key="k", notification_id=1, payload_fingerprint="b")
        == NotificationStartResult.CONFLICT
    )
    await store.mark_failed(dedup_key="k", error_code="failure")
    assert (
        await store.try_start(dedup_key="k", notification_id=1, payload_fingerprint="a")
        == NotificationStartResult.RETRY_ALLOWED
    )
    await store.mark_succeeded(dedup_key="k", external_message_id="om")
    assert (
        await store.try_start(dedup_key="k", notification_id=1, payload_fingerprint="a")
        == NotificationStartResult.ALREADY_SUCCEEDED
    )
    assert await store.get_external_message_id("k") == "om"
