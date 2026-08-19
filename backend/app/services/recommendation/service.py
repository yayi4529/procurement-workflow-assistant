from datetime import datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.repositories.recommendation_core import RecommendationCoreRepository
from app.services.recommendation.candidate_builder import CandidateBuilder
from app.services.recommendation.feature_aggregator import FeatureAggregator
from app.services.recommendation.hard_filter import HardFilter
from app.services.recommendation.normalizer import (
    canonical_item_name,
    normalize_brand,
    normalize_model,
)
from app.services.recommendation.product_ranker import ProductRanker, months_before
from app.services.recommendation.supplier_ranker import SupplierRanker
from app.services.recommendation.types import (
    HISTORY_WINDOW_MONTHS,
    MATCH_ORDER,
    MAX_CANDIDATE_POOL_SIZE,
    MAX_PRODUCT_RECOMMENDATIONS,
    MAX_SUPPLIER_RECOMMENDATIONS,
    TARGET_ELIGIBLE_CANDIDATE_COUNT,
    HistoryEvidence,
    ItemRef,
    ProductRecommendationResult,
    ProductSkipReason,
    SelectedProductRef,
    SupplierFilterResult,
    SupplierRecommendationResult,
)


class RecommendationCoreRepositoryPort(Protocol):
    async def get_item(self, session: AsyncSession, request_item_id: int) -> ItemRef | None: ...

    async def history_for_category(
        self,
        session: AsyncSession,
        *,
        category_id: int,
        exclude_request_item_id: int,
        now: datetime,
    ) -> list[HistoryEvidence]: ...


class RecommendationCoreService:
    def __init__(
        self,
        repository: RecommendationCoreRepositoryPort | None = None,
        candidate_builder: CandidateBuilder | None = None,
        hard_filter: HardFilter | None = None,
        feature_aggregator: FeatureAggregator | None = None,
        product_ranker: ProductRanker | None = None,
        supplier_ranker: SupplierRanker | None = None,
    ) -> None:
        self.repository = repository or RecommendationCoreRepository()
        self.candidate_builder = candidate_builder or CandidateBuilder()
        self.hard_filter = hard_filter or HardFilter()
        self.feature_aggregator = feature_aggregator or FeatureAggregator()
        self.product_ranker = product_ranker or ProductRanker()
        self.supplier_ranker = supplier_ranker or SupplierRanker()

    @staticmethod
    def selected_product_from_item(item: ItemRef) -> SelectedProductRef | None:
        brand = normalize_brand(item.brand)
        model = normalize_model(item.model)
        if item.equipment_model_id is not None:
            key = f"model:{item.equipment_model_id}"
        elif brand and model:
            key = f"snapshot:{brand}:{model}"
        else:
            return None
        return SelectedProductRef(
            product_key=key,
            equipment_category_id=item.equipment_category_id,
            equipment_model_id=item.equipment_model_id,
            item_name=canonical_item_name(item.item_name),
            brand=brand,
            model=model,
        )

    async def _item_and_history(
        self, session: AsyncSession, request_item_id: int, now: datetime
    ) -> tuple[ItemRef, list[HistoryEvidence]]:
        item = await self.repository.get_item(session, request_item_id)
        if item is None:
            raise AppError("REQUEST_ITEM_NOT_FOUND", "采购项不存在", 404)
        if item.equipment_category_id is None:
            return item, []
        history = await self.repository.history_for_category(
            session,
            category_id=item.equipment_category_id,
            exclude_request_item_id=item.request_item_id,
            now=now,
        )
        return item, history

    async def recommend_products(
        self,
        session: AsyncSession,
        request_item_id: int,
        *,
        limit: int = MAX_PRODUCT_RECOMMENDATIONS,
        now: datetime | None = None,
    ) -> ProductRecommendationResult:
        current_time = now or datetime.now()
        item, history = await self._item_and_history(session, request_item_id, current_time)
        if self.selected_product_from_item(item) is not None:
            return ProductRecommendationResult(
                request_item=item,
                recommendations=[],
                skip_reason=ProductSkipReason.PRODUCT_ALREADY_SPECIFIED,
            )
        matched = self.candidate_builder.match_item(
            item, history, stale_before=months_before(current_time, HISTORY_WINDOW_MONTHS)
        )
        candidates = self.candidate_builder.products(matched)
        candidates.sort(
            key=lambda value: (
                MATCH_ORDER.index(value.best_match_level),
                -value.last_purchased_at.timestamp(),
                value.product_key,
            )
        )
        candidates = candidates[:MAX_CANDIDATE_POOL_SIZE]
        ranked = self.product_ranker.rank(candidates, now=current_time, limit=limit)
        return ProductRecommendationResult(item, ranked, None)

    async def recommend_suppliers(
        self,
        session: AsyncSession,
        request_item_id: int,
        selected_product: SelectedProductRef | None = None,
        *,
        limit: int = MAX_SUPPLIER_RECOMMENDATIONS,
        now: datetime | None = None,
    ) -> SupplierRecommendationResult:
        current_time = now or datetime.now()
        item, history = await self._item_and_history(session, request_item_id, current_time)
        selected = selected_product or self.selected_product_from_item(item)
        if selected is None:
            raise AppError(
                "SELECTED_PRODUCT_REQUIRED",
                "采购项尚未明确具体产品，供应商推荐需要 selected_product",
                409,
            )
        if selected.equipment_category_id != item.equipment_category_id:
            raise AppError("SELECTED_PRODUCT_CATEGORY_MISMATCH", "所选产品与采购项类别不一致", 400)
        matched = self.candidate_builder.match_selected_product(
            selected,
            history,
            stale_before=months_before(current_time, HISTORY_WINDOW_MONTHS),
        )
        included = []
        filtered = SupplierFilterResult([], [])
        for level in MATCH_ORDER:
            included.extend(row for row in matched if row.match_level == level)
            raw_candidates = self.candidate_builder.suppliers(included)
            raw_candidates.sort(
                key=lambda value: (
                    MATCH_ORDER.index(value.best_match_level),
                    -value.last_purchased_at.timestamp(),
                    value.supplier_id,
                )
            )
            raw_candidates = raw_candidates[:MAX_CANDIDATE_POOL_SIZE]
            filtered = self.hard_filter.suppliers(raw_candidates)
            if (
                len(filtered.eligible_candidates) >= TARGET_ELIGIBLE_CANDIDATE_COUNT
                or len(raw_candidates) >= MAX_CANDIDATE_POOL_SIZE
            ):
                break
        features = [
            self.feature_aggregator.supplier(candidate)
            for candidate in filtered.eligible_candidates
        ]
        ranked = self.supplier_ranker.rank(filtered.eligible_candidates, features, limit=limit)
        return SupplierRecommendationResult(
            request_item=item,
            selected_product=selected,
            recommendations=ranked,
            excluded_candidates=filtered.excluded_candidates,
        )
