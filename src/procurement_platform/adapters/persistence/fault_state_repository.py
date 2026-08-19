import json
import logging
from decimal import Decimal
from typing import Any

from procurement_platform.adapters.persistence.redis_stores import RedisClient
from procurement_platform.domain.enums import PurchaseItemKind
from procurement_platform.domain.errors import FaultStateRepositoryError
from procurement_platform.domain.fault_guidance import CandidateItem, FaultState

logger = logging.getLogger(__name__)


class FaultStateRepository:
    def __init__(self, client: RedisClient, *, ttl_seconds: int = 86400) -> None:
        if ttl_seconds < 1:
            raise ValueError("fault state TTL must be positive")
        self._client = client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def key(conversation_id: int | str) -> str:
        value = str(conversation_id).strip()
        if not value:
            raise ValueError("conversation_id must not be empty")
        return f"fault_guidance:{value}"

    async def get(self, conversation_id: int | str) -> FaultState | None:
        key = self.key(conversation_id)
        try:
            raw = await self._client.get(key)
            if raw is None:
                return None
            state = self._deserialize(raw)
            await self._client.expire(key, self._ttl_seconds)
            return state
        except Exception as exc:
            logger.exception("fault state Redis read failed key=%s", key)
            raise FaultStateRepositoryError("failed to read fault state from Redis") from exc

    async def save(self, conversation_id: int | str, state: FaultState) -> None:
        key = self.key(conversation_id)
        try:
            await self._client.set(key, self._serialize(state), ex=self._ttl_seconds)
        except Exception as exc:
            logger.exception("fault state Redis write failed key=%s", key)
            raise FaultStateRepositoryError("failed to save fault state to Redis") from exc

    async def delete(self, conversation_id: int | str) -> None:
        key = self.key(conversation_id)
        try:
            await self._client.delete(key)
        except Exception as exc:
            logger.exception("fault state Redis delete failed key=%s", key)
            raise FaultStateRepositoryError("failed to delete fault state from Redis") from exc

    async def reset(self, conversation_id: int | str) -> None:
        await self.delete(conversation_id)

    @staticmethod
    def _serialize(state: FaultState) -> str:
        payload = {
            "source_asset_ref": state.source_asset_ref,
            "issue_summary": state.issue_summary,
            "confirmed_facts": state.confirmed_facts,
            "candidate_items": [
                {
                    "item_kind": item.item_kind.value if item.item_kind is not None else None,
                    "item_name": item.item_name,
                    "quantity": str(item.quantity) if item.quantity is not None else None,
                    "unit": item.unit,
                    "brand": item.brand,
                    "model": item.model,
                    "item_evidence": item.item_evidence,
                    "quantity_evidence": item.quantity_evidence,
                }
                for item in state.candidate_items
            ],
            "knowledge_refs": state.knowledge_refs,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _deserialize(raw: object) -> FaultState:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        payload: Any = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("fault state JSON must be an object")
        raw_items = payload.get("candidate_items", [])
        if not isinstance(raw_items, list):
            raise ValueError("candidate_items must be a list")
        items: list[CandidateItem] = []
        for item in raw_items:
            if not isinstance(item, dict):
                raise ValueError("candidate_items entries must be objects")
            items.append(
                CandidateItem(
                    item_kind=(
                        PurchaseItemKind(item["item_kind"])
                        if item.get("item_kind") is not None
                        else None
                    ),
                    item_name=item["item_name"],
                    quantity=Decimal(item["quantity"])
                    if item.get("quantity") is not None
                    else None,
                    unit=item.get("unit"),
                    brand=item.get("brand"),
                    model=item.get("model"),
                    item_evidence=item.get("item_evidence"),
                    quantity_evidence=item.get("quantity_evidence"),
                )
            )
        confirmed_facts = payload.get("confirmed_facts", {})
        knowledge_refs = payload.get("knowledge_refs", [])
        if (
            not isinstance(confirmed_facts, dict)
            or not isinstance(knowledge_refs, list)
            or not all(isinstance(item, str) for item in knowledge_refs)
        ):
            raise ValueError("fault state collections have invalid types")
        return FaultState(
            source_asset_ref=payload.get("source_asset_ref"),
            issue_summary=payload.get("issue_summary"),
            confirmed_facts=confirmed_facts,
            candidate_items=items,
            knowledge_refs=knowledge_refs,
        )
