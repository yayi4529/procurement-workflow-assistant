from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.services.recommendation.types import (
    CandidateType,
    ExclusionCode,
    MatchLevel,
    ReasonCode,
    WarningCode,
)


class ProductRecommendationStatus(StrEnum):
    OK = "OK"
    PRODUCT_ALREADY_SPECIFIED = "PRODUCT_ALREADY_SPECIFIED"
    NO_HISTORICAL_CANDIDATES = "NO_HISTORICAL_CANDIDATES"


class RecommendationQueryContext(BaseModel):
    request_id: int
    request_item_id: int
    item_name: str
    equipment_category_id: int | None
    equipment_model_id: int | None
    brand: str | None
    model: str | None
    quantity: Decimal
    unit: str


class RecommendationReasonDTO(BaseModel):
    code: ReasonCode
    message: str


class RecommendationWarningDTO(BaseModel):
    code: WarningCode
    message: str


class ProductPriceSummary(BaseModel):
    median_unit_price: Decimal
    min_unit_price: Decimal
    max_unit_price: Decimal
    latest_unit_price: Decimal
    sample_count: int
    currency: str = "CNY"


class ProductScoreBreakdownDTO(BaseModel):
    relevance_score: Decimal
    frequency_score: Decimal
    recency_score: Decimal
    supplier_coverage_score: Decimal
    relevance_weight: Decimal = Decimal("0.50")
    frequency_weight: Decimal = Decimal("0.20")
    recency_weight: Decimal = Decimal("0.15")
    supplier_coverage_weight: Decimal = Decimal("0.15")


class ProductRecommendationItemDTO(BaseModel):
    rank: int
    product_key: str
    equipment_model_id: int | None
    item_name: str
    brand: str | None
    model: str | None
    candidate_type: CandidateType
    match_level: MatchLevel
    overall_score: Decimal
    historical_purchase_count: int
    last_purchased_at: datetime
    active_supplier_count: int
    price_summary: ProductPriceSummary | None
    score_breakdown: ProductScoreBreakdownDTO
    reasons: list[RecommendationReasonDTO]
    warnings: list[RecommendationWarningDTO]


class ProductRecommendationResponse(BaseModel):
    request_item_id: int
    query_context: RecommendationQueryContext
    status: ProductRecommendationStatus
    candidate_count: int
    returned_count: int
    recommendations: list[ProductRecommendationItemDTO]
    warnings: list[RecommendationWarningDTO]
    policy_version: str


class SelectedProductDTO(BaseModel):
    product_key: str = Field(min_length=1, max_length=500)
    equipment_model_id: int | None = None
    equipment_category_id: int | None = None
    item_name: str = Field(min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)

    @model_validator(mode="after")
    def validate_identity(self) -> "SelectedProductDTO":
        if self.equipment_model_id is not None:
            expected = f"model:{self.equipment_model_id}"
            if self.product_key != expected:
                raise ValueError("product_key 与 equipment_model_id 不一致")
        return self


class SupplierRecommendationRequest(BaseModel):
    selected_product: SelectedProductDTO | None = None
    top_k: int = Field(default=5, ge=1, le=5)


class SupplierPriceSummary(BaseModel):
    median_unit_price: Decimal | None
    min_unit_price: Decimal | None
    max_unit_price: Decimal | None
    latest_unit_price: Decimal | None
    sample_count: int
    currency: str = "CNY"


class SupplierDeliverySummary(BaseModel):
    median_delivery_days: Decimal | None
    sample_count: int


class SupplierConfidenceSummary(BaseModel):
    evidence_count: int
    confidence_score: Decimal


class SupplierScoreBreakdownDTO(BaseModel):
    relevance_score: Decimal
    price_score: Decimal | None
    delivery_score: Decimal | None
    confidence_score: Decimal
    relevance_weight: Decimal
    price_weight: Decimal
    delivery_weight: Decimal
    confidence_weight: Decimal
    effective_weight_sum: Decimal


class SupplierRecommendationItemDTO(BaseModel):
    rank: int
    supplier_id: int
    supplier_name: str
    overall_score: Decimal
    match_level: MatchLevel
    history_purchase_count: int
    last_purchase_at: datetime
    price_summary: SupplierPriceSummary
    delivery_summary: SupplierDeliverySummary
    confidence_summary: SupplierConfidenceSummary
    score_breakdown: SupplierScoreBreakdownDTO
    reasons: list[RecommendationReasonDTO]
    warnings: list[RecommendationWarningDTO]


class ExcludedSupplierDTO(BaseModel):
    supplier_id: int
    supplier_name: str
    match_level: MatchLevel
    exclusion_code: ExclusionCode
    exclusion_reason: str


class SupplierRecommendationResponse(BaseModel):
    request_item_id: int
    query_context: RecommendationQueryContext
    selected_product: SelectedProductDTO
    candidate_count: int
    eligible_candidate_count: int
    returned_count: int
    recommendations: list[SupplierRecommendationItemDTO]
    excluded_candidates: list[ExcludedSupplierDTO]
    warnings: list[RecommendationWarningDTO]
    policy_version: str
