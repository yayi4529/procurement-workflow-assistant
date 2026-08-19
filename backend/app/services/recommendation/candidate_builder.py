from collections import defaultdict
from dataclasses import replace
from datetime import datetime

from app.services.recommendation.normalizer import (
    canonical_item_name,
    normalize_brand,
    normalize_model,
)
from app.services.recommendation.types import (
    MATCH_ORDER,
    MATCH_SCORES,
    CandidateType,
    HistoryEvidence,
    ItemRef,
    MatchLevel,
    ProductCandidate,
    ReasonCode,
    SelectedProductRef,
    SupplierCandidate,
    WarningCode,
)


def _product_key(evidence: HistoryEvidence) -> tuple[str, CandidateType]:
    brand = normalize_brand(evidence.brand)
    model = normalize_model(evidence.model)
    if evidence.equipment_model_id is not None:
        return f"model:{evidence.equipment_model_id}", CandidateType.MODEL
    if brand and model:
        return f"snapshot:{brand}:{model}", CandidateType.BRAND_MODEL_SNAPSHOT
    return (
        f"item:{canonical_item_name(evidence.item_name)}:{brand or '-'}",
        CandidateType.GENERIC_HISTORY_ITEM,
    )


def _match(
    *,
    category_id: int | None,
    model_id: int | None,
    item_name: str,
    brand: str | None,
    model: str | None,
    evidence: HistoryEvidence,
) -> MatchLevel | None:
    if category_id is None or evidence.equipment_category_id != category_id:
        return None
    if model_id is not None and evidence.equipment_model_id == model_id:
        return MatchLevel.EXACT_MODEL
    normalized_brand = normalize_brand(brand)
    normalized_model = normalize_model(model)
    if (
        normalized_brand
        and normalized_model
        and normalize_brand(evidence.brand) == normalized_brand
        and normalize_model(evidence.model) == normalized_model
    ):
        return MatchLevel.EXACT_SNAPSHOT
    if canonical_item_name(evidence.item_name) == canonical_item_name(item_name):
        return MatchLevel.SAME_ITEM
    return MatchLevel.SAME_CATEGORY


def _reason(level: MatchLevel) -> ReasonCode:
    return ReasonCode[f"{level.value}_HISTORY"]


class CandidateBuilder:
    def match_item(
        self, current: ItemRef, history: list[HistoryEvidence], *, stale_before: datetime
    ) -> list[HistoryEvidence]:
        matched: list[HistoryEvidence] = []
        for evidence in history:
            level = _match(
                category_id=current.equipment_category_id,
                model_id=current.equipment_model_id,
                item_name=current.item_name,
                brand=current.brand,
                model=current.model,
                evidence=evidence,
            )
            if level is not None:
                matched.append(
                    replace(
                        evidence,
                        match_level=level,
                        stale=evidence.purchased_at < stale_before,
                    )
                )
        return matched

    def match_selected_product(
        self,
        selected: SelectedProductRef,
        history: list[HistoryEvidence],
        *,
        stale_before: datetime,
    ) -> list[HistoryEvidence]:
        matched: list[HistoryEvidence] = []
        for evidence in history:
            level = _match(
                category_id=selected.equipment_category_id,
                model_id=selected.equipment_model_id,
                item_name=selected.item_name,
                brand=selected.brand,
                model=selected.model,
                evidence=evidence,
            )
            if level is not None:
                matched.append(
                    replace(
                        evidence,
                        match_level=level,
                        stale=evidence.purchased_at < stale_before,
                    )
                )
        return matched

    def products(self, matched: list[HistoryEvidence]) -> list[ProductCandidate]:
        grouped: dict[str, list[HistoryEvidence]] = defaultdict(list)
        candidate_types: dict[str, CandidateType] = {}
        for evidence in matched:
            key, candidate_type = _product_key(evidence)
            grouped[key].append(evidence)
            candidate_types[key] = candidate_type
        candidates: list[ProductCandidate] = []
        for key, evidence_rows in grouped.items():
            best = min(
                (row.match_level for row in evidence_rows if row.match_level is not None),
                key=MATCH_ORDER.index,
            )
            latest = max(evidence_rows, key=lambda row: row.purchased_at)
            active_supplier_ids = {
                row.supplier_id
                for row in evidence_rows
                if row.supplier_active and not row.active_blacklist
            }
            warnings = {WarningCode.COMPATIBILITY_NOT_VERIFIED}
            if any(row.stale for row in evidence_rows):
                warnings.add(WarningCode.STALE_HISTORY)
            if not active_supplier_ids:
                warnings.add(WarningCode.NO_ACTIVE_SUPPLIER)
            reasons = {_reason(best)}
            if len(evidence_rows) >= 4:
                reasons.add(ReasonCode.STRONG_HISTORY)
            if not all(row.stale for row in evidence_rows):
                reasons.add(ReasonCode.RECENT_HISTORY)
            if len(active_supplier_ids) >= 2:
                reasons.add(ReasonCode.MULTIPLE_ACTIVE_SUPPLIERS)
            candidates.append(
                ProductCandidate(
                    product_key=key,
                    equipment_model_id=latest.equipment_model_id,
                    item_name=latest.item_name,
                    brand=latest.brand,
                    model=latest.model,
                    candidate_type=candidate_types[key],
                    best_match_level=best,
                    relevance_score=MATCH_SCORES[best],
                    historical_purchase_count=len(evidence_rows),
                    last_purchased_at=latest.purchased_at,
                    supplier_ids={row.supplier_id for row in evidence_rows},
                    active_supplier_ids=active_supplier_ids,
                    history_item_ids={row.request_item_id for row in evidence_rows},
                    execution_ids={row.execution_id for row in evidence_rows},
                    warnings=warnings,
                    reasons=reasons,
                )
            )
        return candidates

    def suppliers(self, matched: list[HistoryEvidence]) -> list[SupplierCandidate]:
        grouped: dict[int, list[HistoryEvidence]] = defaultdict(list)
        for evidence in matched:
            grouped[evidence.supplier_id].append(evidence)
        candidates: list[SupplierCandidate] = []
        for supplier_id, rows in grouped.items():
            levels = [row.match_level for row in rows if row.match_level is not None]
            best = min(levels, key=MATCH_ORDER.index)
            strict = [row for row in rows if row.match_level == best]
            latest = max(strict, key=lambda row: row.purchased_at)
            warnings = {WarningCode.COMPATIBILITY_NOT_VERIFIED}
            if len(strict) == 1:
                warnings.add(WarningCode.LOW_SAMPLE_SIZE)
            if any(row.stale for row in strict):
                warnings.add(WarningCode.STALE_HISTORY)
            match_counts = {level: levels.count(level) for level in MATCH_ORDER if level in levels}
            candidates.append(
                SupplierCandidate(
                    supplier_id=supplier_id,
                    supplier_name=latest.supplier_name,
                    supplier_active=latest.supplier_active,
                    active_blacklist=latest.active_blacklist,
                    best_match_level=best,
                    relevance_score=MATCH_SCORES[best],
                    historical_purchase_count=len(rows),
                    last_purchased_at=latest.purchased_at,
                    match_counts=match_counts,
                    evidence_scope=best,
                    evidence_item_ids={row.request_item_id for row in strict},
                    execution_ids={row.execution_id for row in strict},
                    product_keys={_product_key(row)[0] for row in strict},
                    evidence=strict,
                    warnings=warnings,
                    reasons={_reason(best)},
                )
            )
        return candidates
