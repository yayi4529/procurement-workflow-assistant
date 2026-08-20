from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

TARGET_ELIGIBLE_CANDIDATE_COUNT = 10
MAX_CANDIDATE_POOL_SIZE = 20
MAX_SUPPLIER_RECOMMENDATIONS = 5
MAX_PRODUCT_RECOMMENDATIONS = 10
RECOMMENDATION_POLICY_VERSION = "task08-v1"
HISTORY_WINDOW_MONTHS = 24


class MatchLevel(StrEnum):
    EXACT_MODEL = "EXACT_MODEL"
    EXACT_SNAPSHOT = "EXACT_SNAPSHOT"
    SAME_ITEM = "SAME_ITEM"
    SAME_CATEGORY = "SAME_CATEGORY"


MATCH_SCORES = {
    MatchLevel.EXACT_MODEL: Decimal("100"),
    MatchLevel.EXACT_SNAPSHOT: Decimal("95"),
    MatchLevel.SAME_ITEM: Decimal("80"),
    MatchLevel.SAME_CATEGORY: Decimal("60"),
}
MATCH_ORDER = tuple(MatchLevel)


class CandidateType(StrEnum):
    MODEL = "MODEL"
    BRAND_MODEL_SNAPSHOT = "BRAND_MODEL_SNAPSHOT"
    GENERIC_HISTORY_ITEM = "GENERIC_HISTORY_ITEM"


class WarningCode(StrEnum):
    NO_PRICE_DATA = "NO_PRICE_DATA"
    NO_DELIVERY_DATA = "NO_DELIVERY_DATA"
    LOW_SAMPLE_SIZE = "LOW_SAMPLE_SIZE"
    STALE_HISTORY = "STALE_HISTORY"
    NO_ACTIVE_SUPPLIER = "NO_ACTIVE_SUPPLIER"
    COMPATIBILITY_NOT_VERIFIED = "COMPATIBILITY_NOT_VERIFIED"


class ExclusionCode(StrEnum):
    ACTIVE_BLACKLIST = "ACTIVE_BLACKLIST"
    SUPPLIER_INACTIVE = "SUPPLIER_INACTIVE"
    NO_EXECUTION_HISTORY = "NO_EXECUTION_HISTORY"


class ReasonCode(StrEnum):
    EXACT_MODEL_HISTORY = "EXACT_MODEL_HISTORY"
    EXACT_SNAPSHOT_HISTORY = "EXACT_SNAPSHOT_HISTORY"
    SAME_ITEM_HISTORY = "SAME_ITEM_HISTORY"
    SAME_CATEGORY_HISTORY = "SAME_CATEGORY_HISTORY"
    STRONG_HISTORY = "STRONG_HISTORY"
    RECENT_HISTORY = "RECENT_HISTORY"
    MULTIPLE_ACTIVE_SUPPLIERS = "MULTIPLE_ACTIVE_SUPPLIERS"
    COMPETITIVE_PRICE = "COMPETITIVE_PRICE"
    FAST_DELIVERY = "FAST_DELIVERY"


class ProductSkipReason(StrEnum):
    PRODUCT_ALREADY_SPECIFIED = "PRODUCT_ALREADY_SPECIFIED"


@dataclass(frozen=True)
class ItemRef:
    request_id: int
    request_item_id: int
    equipment_category_id: int | None
    equipment_model_id: int | None
    item_name: str
    brand: str | None
    model: str | None
    requires_warehouse: bool


@dataclass(frozen=True)
class SelectedProductRef:
    product_key: str
    equipment_category_id: int | None
    equipment_model_id: int | None
    item_name: str
    brand: str | None
    model: str | None


@dataclass(frozen=True)
class HistoryEvidence:
    request_id: int
    request_item_id: int
    equipment_category_id: int | None
    equipment_model_id: int | None
    item_name: str
    brand: str | None
    model: str | None
    requires_warehouse: bool
    execution_id: int
    supplier_id: int
    supplier_name: str
    supplier_active: bool
    actual_unit_price: Decimal | None
    purchased_at: datetime
    final_received_at: datetime | None
    active_blacklist: bool = False
    match_level: MatchLevel | None = None
    stale: bool = False


@dataclass
class ProductCandidate:
    product_key: str
    equipment_model_id: int | None
    item_name: str
    brand: str | None
    model: str | None
    candidate_type: CandidateType
    best_match_level: MatchLevel
    relevance_score: Decimal
    historical_purchase_count: int
    last_purchased_at: datetime
    supplier_ids: set[int] = field(default_factory=set)
    active_supplier_ids: set[int] = field(default_factory=set)
    history_item_ids: set[int] = field(default_factory=set)
    execution_ids: set[int] = field(default_factory=set)
    warnings: set[WarningCode] = field(default_factory=set)
    reasons: set[ReasonCode] = field(default_factory=set)


@dataclass
class SupplierCandidate:
    supplier_id: int
    supplier_name: str
    supplier_active: bool
    active_blacklist: bool
    best_match_level: MatchLevel
    relevance_score: Decimal
    historical_purchase_count: int
    last_purchased_at: datetime
    match_counts: dict[MatchLevel, int]
    evidence_scope: MatchLevel
    evidence_item_ids: set[int]
    execution_ids: set[int]
    product_keys: set[str]
    evidence: list[HistoryEvidence]
    warnings: set[WarningCode] = field(default_factory=set)
    reasons: set[ReasonCode] = field(default_factory=set)


@dataclass(frozen=True)
class ExcludedSupplierCandidate:
    supplier_id: int
    supplier_name: str
    match_level: MatchLevel
    exclusion_code: ExclusionCode
    exclusion_reason: str


@dataclass(frozen=True)
class SupplierFilterResult:
    eligible_candidates: list[SupplierCandidate]
    excluded_candidates: list[ExcludedSupplierCandidate]


@dataclass(frozen=True)
class SupplierFeatures:
    supplier_id: int
    history_purchase_count: int
    last_purchase_at: datetime
    median_unit_price: Decimal | None
    min_unit_price: Decimal | None
    max_unit_price: Decimal | None
    latest_unit_price: Decimal | None
    price_sample_count: int
    median_delivery_days: Decimal | None
    delivery_sample_count: int
    evidence_count: int
    warnings: frozenset[WarningCode]


@dataclass(frozen=True)
class SupplierScoreBreakdown:
    relevance_score: Decimal
    price_score: Decimal | None
    delivery_score: Decimal | None
    confidence_score: Decimal
    relevance_weight: Decimal
    price_weight: Decimal
    delivery_weight: Decimal
    confidence_weight: Decimal


@dataclass(frozen=True)
class RankedSupplier:
    rank: int
    candidate: SupplierCandidate
    features: SupplierFeatures
    overall_score: Decimal
    score_breakdown: SupplierScoreBreakdown


@dataclass(frozen=True)
class ProductScoreBreakdown:
    relevance_score: Decimal
    frequency_score: Decimal
    recency_score: Decimal
    supplier_coverage_score: Decimal


@dataclass(frozen=True)
class RankedProduct:
    rank: int
    candidate: ProductCandidate
    overall_score: Decimal
    score_breakdown: ProductScoreBreakdown


@dataclass(frozen=True)
class ProductRecommendationResult:
    request_item: ItemRef
    recommendations: list[RankedProduct]
    skip_reason: ProductSkipReason | None
    policy_version: str = RECOMMENDATION_POLICY_VERSION


@dataclass(frozen=True)
class SupplierRecommendationResult:
    request_item: ItemRef
    selected_product: SelectedProductRef
    recommendations: list[RankedSupplier]
    excluded_candidates: list[ExcludedSupplierCandidate]
    policy_version: str = RECOMMENDATION_POLICY_VERSION
