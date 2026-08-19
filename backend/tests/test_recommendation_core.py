from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.services.recommendation.candidate_builder import CandidateBuilder
from app.services.recommendation.feature_aggregator import FeatureAggregator
from app.services.recommendation.hard_filter import HardFilter
from app.services.recommendation.normalizer import normalize_brand, normalize_model
from app.services.recommendation.product_ranker import ProductRanker, recency_score
from app.services.recommendation.service import RecommendationCoreService
from app.services.recommendation.supplier_ranker import SupplierRanker, confidence_score
from app.services.recommendation.types import (
    CandidateType,
    ExclusionCode,
    HistoryEvidence,
    ItemRef,
    MatchLevel,
    ProductCandidate,
    ProductSkipReason,
    SelectedProductRef,
    SupplierCandidate,
    WarningCode,
)

NOW = datetime(2026, 8, 19, 12, 0)


def item(
    item_id: int = 1,
    *,
    category_id: int | None = 10,
    model_id: int | None = None,
    name: str = "UPS 蓄电池",
    brand: str | None = None,
    model: str | None = None,
) -> ItemRef:
    return ItemRef(100, item_id, category_id, model_id, name, brand, model, True)


def evidence(
    execution_id: int,
    *,
    item_id: int | None = None,
    category_id: int = 10,
    model_id: int | None = None,
    name: str = "UPS蓄电池",
    brand: str | None = "Panasonic",
    model: str | None = "LC-P12100",
    supplier_id: int = 1,
    active: bool = True,
    blacklisted: bool = False,
    price: Decimal | None = Decimal("100"),
    purchased_at: datetime = NOW - timedelta(days=10),
    received_at: datetime | None = NOW - timedelta(days=5),
    requires_warehouse: bool = True,
) -> HistoryEvidence:
    return HistoryEvidence(
        request_id=200 + execution_id,
        request_item_id=item_id or 1000 + execution_id,
        equipment_category_id=category_id,
        equipment_model_id=model_id,
        item_name=name,
        brand=brand,
        model=model,
        requires_warehouse=requires_warehouse,
        execution_id=execution_id,
        supplier_id=supplier_id,
        supplier_name=f"Supplier {supplier_id}",
        supplier_active=active,
        actual_unit_price=price,
        purchased_at=purchased_at,
        final_received_at=received_at,
        active_blacklist=blacklisted,
    )


def supplier_candidate(
    supplier_id: int,
    rows: list[HistoryEvidence],
    *,
    relevance: Decimal = Decimal("100"),
) -> SupplierCandidate:
    level = rows[0].match_level or MatchLevel.EXACT_MODEL
    return SupplierCandidate(
        supplier_id=supplier_id,
        supplier_name=f"Supplier {supplier_id}",
        supplier_active=rows[0].supplier_active,
        active_blacklist=rows[0].active_blacklist,
        best_match_level=level,
        relevance_score=relevance,
        historical_purchase_count=len(rows),
        last_purchased_at=max(row.purchased_at for row in rows),
        match_counts={level: len(rows)},
        evidence_scope=level,
        evidence_item_ids={row.request_item_id for row in rows},
        execution_ids={row.execution_id for row in rows},
        product_keys={"model:7"},
        evidence=rows,
    )


def matched(row: HistoryEvidence, level: MatchLevel = MatchLevel.EXACT_MODEL) -> HistoryEvidence:
    return replace(row, match_level=level)


def test_normalizer_is_deterministic_and_does_not_fuzzy_match_models() -> None:
    assert normalize_brand(" 华为 ") == "HUAWEI"
    assert normalize_brand("Huawei") == "HUAWEI"
    assert normalize_model("lc-p12 100") == "LCP12100"
    assert normalize_model("LC-P12100") != normalize_model("LC-P12120")


def test_candidate_builder_match_levels_and_category_boundary() -> None:
    builder = CandidateBuilder()
    current = item(model_id=7, brand="Panasonic", model="LC P12100")
    rows = [
        evidence(1, model_id=7),
        evidence(2, model_id=None, brand="panasonic", model="LC_P12100"),
        evidence(3, model_id=None, brand=None, model=None),
        evidence(4, model_id=None, name="其他电池", brand=None, model=None),
        evidence(5, category_id=99, model_id=7),
    ]
    result = builder.match_item(current, rows, stale_before=NOW - timedelta(days=730))
    assert [row.match_level for row in result] == [
        MatchLevel.EXACT_MODEL,
        MatchLevel.EXACT_SNAPSHOT,
        MatchLevel.SAME_ITEM,
        MatchLevel.SAME_CATEGORY,
    ]


def test_product_candidates_aggregate_only_executed_history() -> None:
    builder = CandidateBuilder()
    rows = builder.match_item(
        item(), [evidence(1), evidence(2, supplier_id=2)], stale_before=NOW - timedelta(days=730)
    )
    products = builder.products(rows)
    assert len(products) == 1
    assert products[0].candidate_type == CandidateType.BRAND_MODEL_SNAPSHOT
    assert products[0].historical_purchase_count == 2
    assert products[0].active_supplier_ids == {1, 2}


def test_supplier_strict_evidence_scope_excludes_weaker_matches() -> None:
    builder = CandidateBuilder()
    exact = matched(evidence(1, model_id=7), MatchLevel.EXACT_MODEL)
    weaker = matched(evidence(2, model_id=None), MatchLevel.SAME_ITEM)
    candidate = builder.suppliers([exact, weaker])[0]
    assert candidate.evidence_scope == MatchLevel.EXACT_MODEL
    assert candidate.execution_ids == {1}
    assert candidate.historical_purchase_count == 2


@pytest.mark.parametrize(
    ("active", "blacklisted", "expected"),
    [
        (True, True, ExclusionCode.ACTIVE_BLACKLIST),
        (False, False, ExclusionCode.SUPPLIER_INACTIVE),
    ],
)
def test_hard_filter_preserves_exclusion_reason(
    active: bool, blacklisted: bool, expected: ExclusionCode
) -> None:
    row = matched(evidence(1, active=active, blacklisted=blacklisted))
    result = HardFilter().suppliers([supplier_candidate(1, [row])])
    assert not result.eligible_candidates
    assert result.excluded_candidates[0].exclusion_code == expected


def test_feature_aggregator_uses_medians_latest_and_final_receipt() -> None:
    rows = [
        matched(
            evidence(
                1,
                price=Decimal("100"),
                purchased_at=NOW - timedelta(days=20),
                received_at=NOW - timedelta(days=15),
            )
        ),
        matched(
            evidence(
                2,
                price=Decimal("300"),
                purchased_at=NOW - timedelta(days=10),
                received_at=NOW - timedelta(days=1),
            )
        ),
    ]
    features = FeatureAggregator().supplier(supplier_candidate(1, rows))
    assert features.median_unit_price == Decimal("200")
    assert features.min_unit_price == Decimal("100")
    assert features.max_unit_price == Decimal("300")
    assert features.latest_unit_price == Decimal("300")
    assert features.median_delivery_days == Decimal("7")
    assert features.evidence_count == 2


def test_feature_aggregator_does_not_invent_price_or_delivery() -> None:
    row = matched(evidence(1, price=None, received_at=None, requires_warehouse=False))
    features = FeatureAggregator().supplier(supplier_candidate(1, [row]))
    assert features.median_unit_price is None
    assert features.median_delivery_days is None
    assert WarningCode.NO_PRICE_DATA in features.warnings
    assert WarningCode.NO_DELIVERY_DATA in features.warnings


def test_supplier_ranker_renormalizes_missing_features_and_is_stable() -> None:
    candidates = []
    features = []
    for supplier_id in (2, 1):
        row = matched(evidence(supplier_id, supplier_id=supplier_id, price=None, received_at=None))
        candidate = supplier_candidate(supplier_id, [row])
        candidates.append(candidate)
        features.append(FeatureAggregator().supplier(candidate))
    ranked = SupplierRanker().rank(candidates, features)
    assert [value.candidate.supplier_id for value in ranked] == [1, 2]
    assert ranked[0].overall_score == Decimal("88")
    assert ranked[0].score_breakdown.relevance_weight == Decimal("0.8")
    assert ranked[0].score_breakdown.confidence_weight == Decimal("0.2")


def test_supplier_price_and_delivery_scores_use_best_candidate_as_100() -> None:
    candidates = []
    features = []
    for supplier_id, price, days in ((1, "100", 4), (2, "200", 8)):
        row = matched(
            evidence(
                supplier_id,
                supplier_id=supplier_id,
                price=Decimal(price),
                purchased_at=NOW - timedelta(days=10),
                received_at=NOW - timedelta(days=10 - days),
            )
        )
        candidate = supplier_candidate(supplier_id, [row])
        candidates.append(candidate)
        features.append(FeatureAggregator().supplier(candidate))
    ranked = SupplierRanker().rank(candidates, features)
    assert ranked[0].score_breakdown.price_score == Decimal("100")
    assert ranked[0].score_breakdown.delivery_score == Decimal("100")
    assert ranked[1].score_breakdown.price_score == Decimal("50")
    assert ranked[1].score_breakdown.delivery_score == Decimal("50")


@pytest.mark.parametrize(("count", "score"), [(1, 40), (2, 60), (4, 80), (7, 100)])
def test_confidence_bands(count: int, score: int) -> None:
    assert confidence_score(count) == score


def test_product_ranker_formula_boundaries_and_tie_break() -> None:
    candidates = [
        ProductCandidate(
            product_key=key,
            equipment_model_id=None,
            item_name="UPS蓄电池",
            brand=None,
            model=None,
            candidate_type=CandidateType.GENERIC_HISTORY_ITEM,
            best_match_level=MatchLevel.SAME_ITEM,
            relevance_score=Decimal("80"),
            historical_purchase_count=1,
            last_purchased_at=NOW - timedelta(days=1),
            active_supplier_ids={1},
        )
        for key in ("item:B:-", "item:A:-")
    ]
    ranked = ProductRanker().rank(candidates, now=NOW)
    assert [value.candidate.product_key for value in ranked] == ["item:A:-", "item:B:-"]
    assert ranked[0].overall_score == Decimal("69.00")
    assert recency_score(datetime(2026, 2, 19, 12), NOW) == 100
    assert recency_score(datetime(2026, 2, 18, 12), NOW) == 80
    assert recency_score(datetime(2025, 8, 19, 12), NOW) == 80
    assert recency_score(datetime(2024, 8, 18, 12), NOW) == 40


class FakeRepository:
    def __init__(
        self, items: dict[int, ItemRef], history: dict[int, list[HistoryEvidence]]
    ) -> None:
        self.items = items
        self.history = history

    async def get_item(self, session: AsyncSession, request_item_id: int) -> ItemRef | None:
        return self.items.get(request_item_id)

    async def history_for_category(
        self,
        session: AsyncSession,
        *,
        category_id: int,
        exclude_request_item_id: int,
        now: datetime,
    ) -> list[HistoryEvidence]:
        return self.history.get(exclude_request_item_id, [])


@pytest.mark.asyncio
async def test_service_skips_product_ranking_when_model_is_specified() -> None:
    current = item(model_id=7)
    service = RecommendationCoreService(repository=FakeRepository({1: current}, {}))
    result = await service.recommend_products(cast(AsyncSession, object()), 1, now=NOW)
    assert result.skip_reason == ProductSkipReason.PRODUCT_ALREADY_SPECIFIED
    assert not result.recommendations


@pytest.mark.asyncio
async def test_service_requires_selected_product_for_generic_item() -> None:
    service = RecommendationCoreService(repository=FakeRepository({1: item()}, {}))
    with pytest.raises(AppError) as raised:
        await service.recommend_suppliers(cast(AsyncSession, object()), 1, now=NOW)
    assert raised.value.code == "SELECTED_PRODUCT_REQUIRED"


@pytest.mark.asyncio
async def test_service_keeps_request_items_isolated_and_caps_pool() -> None:
    items = {1: item(1), 2: item(2, name="温度传感器")}
    histories = {
        1: [evidence(index, model=f"MODEL-{index}") for index in range(1, 26)],
        2: [evidence(30, name="温度传感器", brand="Acme", model="T-1")],
    }
    service = RecommendationCoreService(repository=FakeRepository(items, histories))
    first = await service.recommend_products(cast(AsyncSession, object()), 1, now=NOW)
    second = await service.recommend_products(cast(AsyncSession, object()), 2, now=NOW)
    assert len(first.recommendations) == 10
    assert len(second.recommendations) == 1
    assert (
        first.recommendations[0].candidate.product_key
        != second.recommendations[0].candidate.product_key
    )


@pytest.mark.asyncio
async def test_service_supplier_expansion_retains_excluded_candidates() -> None:
    current = item(model_id=7, brand="Panasonic", model="LC-P12100")
    rows = [
        evidence(1, model_id=7, blacklisted=True),
        evidence(2, model_id=7, supplier_id=2),
        evidence(3, model_id=None, supplier_id=3),
    ]
    service = RecommendationCoreService(repository=FakeRepository({1: current}, {1: rows}))
    result = await service.recommend_suppliers(cast(AsyncSession, object()), 1, now=NOW)
    assert [row.candidate.supplier_id for row in result.recommendations] == [2, 3]
    assert result.excluded_candidates[0].supplier_id == 1


def test_selected_product_category_must_match_item() -> None:
    selected = SelectedProductRef("model:1", 99, 1, "other", None, None)
    assert selected.equipment_category_id != item().equipment_category_id
