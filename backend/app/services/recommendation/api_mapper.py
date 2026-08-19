from app.models.procurement import PurchaseRequestItem
from app.schemas.recommendations_v2 import (
    ExcludedSupplierDTO,
    ProductRecommendationItemDTO,
    ProductRecommendationResponse,
    ProductRecommendationStatus,
    ProductScoreBreakdownDTO,
    RecommendationQueryContext,
    RecommendationReasonDTO,
    RecommendationWarningDTO,
    SelectedProductDTO,
    SupplierConfidenceSummary,
    SupplierDeliverySummary,
    SupplierPriceSummary,
    SupplierRecommendationItemDTO,
    SupplierRecommendationResponse,
    SupplierScoreBreakdownDTO,
)
from app.services.recommendation.types import (
    ProductRecommendationResult,
    ProductSkipReason,
    ReasonCode,
    SupplierRecommendationResult,
    WarningCode,
)

WARNING_MESSAGES = {
    WarningCode.NO_PRICE_DATA: "没有可用于评分的历史价格数据",
    WarningCode.NO_DELIVERY_DATA: "没有可用于评分的历史交期数据",
    WarningCode.LOW_SAMPLE_SIZE: "最高相关层级的历史样本较少",
    WarningCode.STALE_HISTORY: "推荐证据包含超过24个月的历史记录",
    WarningCode.NO_ACTIVE_SUPPLIER: "该产品没有当前有效且未被拉黑的历史供应商",
    WarningCode.COMPATIBILITY_NOT_VERIFIED: "历史采购证据不代表已完成兼容性认证",
}
REASON_MESSAGES = {
    ReasonCode.EXACT_MODEL_HISTORY: "存在相同设备型号的历史采购记录",
    ReasonCode.EXACT_SNAPSHOT_HISTORY: "存在相同品牌和型号快照的历史采购记录",
    ReasonCode.SAME_ITEM_HISTORY: "存在同类别同采购对象的历史采购记录",
    ReasonCode.SAME_CATEGORY_HISTORY: "存在同设备类别的历史采购记录",
    ReasonCode.STRONG_HISTORY: "历史采购证据较为充分",
    ReasonCode.RECENT_HISTORY: "存在最近24个月内的采购记录",
    ReasonCode.MULTIPLE_ACTIVE_SUPPLIERS: "存在多家当前有效的历史供应商",
    ReasonCode.COMPETITIVE_PRICE: "历史中位价格在候选中具有竞争力",
    ReasonCode.FAST_DELIVERY: "历史中位交期在候选中较短",
}


def _warning(code: WarningCode) -> RecommendationWarningDTO:
    return RecommendationWarningDTO(code=code, message=WARNING_MESSAGES[code])


def _reason(code: ReasonCode) -> RecommendationReasonDTO:
    return RecommendationReasonDTO(code=code, message=REASON_MESSAGES[code])


def _context(item: PurchaseRequestItem) -> RecommendationQueryContext:
    return RecommendationQueryContext(
        request_id=item.request_id,
        request_item_id=item.request_item_id,
        item_name=item.item_name,
        equipment_category_id=item.equipment_category_id,
        equipment_model_id=item.equipment_model_id,
        brand=item.brand_snapshot,
        model=item.model_snapshot,
        quantity=item.quantity,
        unit=item.unit,
    )


def map_product_result(
    result: ProductRecommendationResult, item: PurchaseRequestItem
) -> ProductRecommendationResponse:
    recommendations = [
        ProductRecommendationItemDTO(
            rank=ranked.rank,
            product_key=ranked.candidate.product_key,
            equipment_model_id=ranked.candidate.equipment_model_id,
            item_name=ranked.candidate.item_name,
            brand=ranked.candidate.brand,
            model=ranked.candidate.model,
            candidate_type=ranked.candidate.candidate_type,
            match_level=ranked.candidate.best_match_level,
            overall_score=ranked.overall_score,
            historical_purchase_count=ranked.candidate.historical_purchase_count,
            last_purchased_at=ranked.candidate.last_purchased_at,
            active_supplier_count=len(ranked.candidate.active_supplier_ids),
            price_summary=None,
            score_breakdown=ProductScoreBreakdownDTO(
                relevance_score=ranked.score_breakdown.relevance_score,
                frequency_score=ranked.score_breakdown.frequency_score,
                recency_score=ranked.score_breakdown.recency_score,
                supplier_coverage_score=ranked.score_breakdown.supplier_coverage_score,
            ),
            reasons=[_reason(code) for code in sorted(ranked.candidate.reasons)],
            warnings=[_warning(code) for code in sorted(ranked.candidate.warnings)],
        )
        for ranked in result.recommendations
    ]
    response_warning_codes = sorted(
        {warning.code for recommendation in recommendations for warning in recommendation.warnings}
    )
    if result.skip_reason == ProductSkipReason.PRODUCT_ALREADY_SPECIFIED:
        status = ProductRecommendationStatus.PRODUCT_ALREADY_SPECIFIED
    elif not recommendations:
        status = ProductRecommendationStatus.NO_HISTORICAL_CANDIDATES
    else:
        status = ProductRecommendationStatus.OK
    return ProductRecommendationResponse(
        request_item_id=item.request_item_id,
        query_context=_context(item),
        status=status,
        candidate_count=len(recommendations),
        returned_count=len(recommendations),
        recommendations=recommendations,
        warnings=[_warning(code) for code in response_warning_codes],
        policy_version=result.policy_version,
    )


def map_supplier_result(
    result: SupplierRecommendationResult, item: PurchaseRequestItem
) -> SupplierRecommendationResponse:
    recommendations = []
    for ranked in result.recommendations:
        breakdown = ranked.score_breakdown
        effective_weight_sum = (
            breakdown.relevance_weight
            + breakdown.price_weight
            + breakdown.delivery_weight
            + breakdown.confidence_weight
        )
        recommendations.append(
            SupplierRecommendationItemDTO(
                rank=ranked.rank,
                supplier_id=ranked.candidate.supplier_id,
                supplier_name=ranked.candidate.supplier_name,
                overall_score=ranked.overall_score,
                match_level=ranked.candidate.best_match_level,
                history_purchase_count=ranked.candidate.historical_purchase_count,
                last_purchase_at=ranked.features.last_purchase_at,
                price_summary=SupplierPriceSummary(
                    median_unit_price=ranked.features.median_unit_price,
                    min_unit_price=ranked.features.min_unit_price,
                    max_unit_price=ranked.features.max_unit_price,
                    latest_unit_price=ranked.features.latest_unit_price,
                    sample_count=ranked.features.price_sample_count,
                ),
                delivery_summary=SupplierDeliverySummary(
                    median_delivery_days=ranked.features.median_delivery_days,
                    sample_count=ranked.features.delivery_sample_count,
                ),
                confidence_summary=SupplierConfidenceSummary(
                    evidence_count=ranked.features.evidence_count,
                    confidence_score=breakdown.confidence_score,
                ),
                score_breakdown=SupplierScoreBreakdownDTO(
                    relevance_score=breakdown.relevance_score,
                    price_score=breakdown.price_score,
                    delivery_score=breakdown.delivery_score,
                    confidence_score=breakdown.confidence_score,
                    relevance_weight=breakdown.relevance_weight,
                    price_weight=breakdown.price_weight,
                    delivery_weight=breakdown.delivery_weight,
                    confidence_weight=breakdown.confidence_weight,
                    effective_weight_sum=effective_weight_sum,
                ),
                reasons=[_reason(code) for code in sorted(ranked.candidate.reasons)],
                warnings=[_warning(code) for code in sorted(ranked.features.warnings)],
            )
        )
    response_warning_codes = sorted(
        {warning.code for recommendation in recommendations for warning in recommendation.warnings}
    )
    selected = result.selected_product
    excluded = [
        ExcludedSupplierDTO(
            supplier_id=candidate.supplier_id,
            supplier_name=candidate.supplier_name,
            match_level=candidate.match_level,
            exclusion_code=candidate.exclusion_code,
            exclusion_reason=candidate.exclusion_reason,
        )
        for candidate in result.excluded_candidates
    ]
    return SupplierRecommendationResponse(
        request_item_id=item.request_item_id,
        query_context=_context(item),
        selected_product=SelectedProductDTO(
            product_key=selected.product_key,
            equipment_model_id=selected.equipment_model_id,
            equipment_category_id=selected.equipment_category_id,
            item_name=selected.item_name,
            brand=selected.brand,
            model=selected.model,
        ),
        candidate_count=len(recommendations) + len(excluded),
        eligible_candidate_count=len(recommendations),
        returned_count=len(recommendations),
        recommendations=recommendations,
        excluded_candidates=excluded,
        warnings=[_warning(code) for code in response_warning_codes],
        policy_version=result.policy_version,
    )
