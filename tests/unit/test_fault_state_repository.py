from decimal import Decimal

from procurement_platform.adapters.persistence.fault_state_repository import (
    FaultStateRepository,
)
from procurement_platform.domain.enums import PurchaseItemKind
from procurement_platform.domain.errors import FaultStateRepositoryError
from procurement_platform.domain.fault_guidance import CandidateItem, FaultState


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.expire_calls: list[tuple[str, int]] = []

    async def get(self, key: str) -> object:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> object:
        self.values[key] = value
        self.ttls[key] = ex
        return True

    async def delete(self, key: str) -> object:
        self.values.pop(key, None)
        self.ttls.pop(key, None)
        return 1

    async def expire(self, key: str, seconds: int) -> object:
        self.ttls[key] = seconds
        self.expire_calls.append((key, seconds))
        return True

    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object:
        del script, numkeys, keys_and_args
        return 1


class FailingRedis(MemoryRedis):
    async def get(self, key: str) -> object:
        del key
        raise ConnectionError("redis unavailable")


async def test_missing_fault_state_returns_none() -> None:
    repository = FaultStateRepository(MemoryRedis())
    assert await repository.get("conv_missing") is None


async def test_fault_state_round_trip_and_get_refreshes_ttl() -> None:
    redis = MemoryRedis()
    repository = FaultStateRepository(redis, ttl_seconds=86400)
    state = FaultState(
        source_asset_ref="asset:108",
        issue_summary="2号UPS出现BATTERY FAULT",
        confirmed_facts={
            "alarm_code": "BATTERY FAULT",
            "inspection_done": True,
            "abnormal_battery_count": 3,
        },
        candidate_items=[
            CandidateItem(
                item_kind=PurchaseItemKind.COMPONENT,
                item_name="UPS蓄电池",
                quantity=Decimal("3.50"),
                unit="块",
                item_evidence="KNOWLEDGE:UPS-BATTERY-001",
                quantity_evidence="USER_CONFIRMED",
            )
        ],
        knowledge_refs=["UPS-BATTERY-001"],
    )
    await repository.save("conv_123456", state)
    loaded = await repository.get("conv_123456")
    assert loaded == state
    assert redis.ttls["fault_guidance:conv_123456"] == 86400
    assert redis.expire_calls == [("fault_guidance:conv_123456", 86400)]
    assert '"quantity":"3.50"' in redis.values["fault_guidance:conv_123456"]
    assert "UPS蓄电池异常" not in redis.values["fault_guidance:conv_123456"]


async def test_save_refreshes_full_ttl() -> None:
    redis = MemoryRedis()
    repository = FaultStateRepository(redis, ttl_seconds=120)
    await repository.save(42, FaultState(issue_summary="first"))
    redis.ttls["fault_guidance:42"] = 1
    await repository.save(42, FaultState(issue_summary="updated"))
    assert redis.ttls["fault_guidance:42"] == 120


async def test_delete_and_reset_remove_fault_state() -> None:
    redis = MemoryRedis()
    repository = FaultStateRepository(redis)
    await repository.save("delete", FaultState(issue_summary="delete me"))
    await repository.delete("delete")
    assert await repository.get("delete") is None
    await repository.save("reset", FaultState(issue_summary="reset me"))
    await repository.reset("reset")
    assert await repository.get("reset") is None


async def test_redis_errors_are_wrapped_without_fallback() -> None:
    repository = FaultStateRepository(FailingRedis())
    try:
        await repository.get("failure")
    except FaultStateRepositoryError as exc:
        assert "Redis" in str(exc)
    else:
        raise AssertionError("Redis infrastructure errors must be propagated")
