from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.domain.enums import RoleCode
from app.domain.identity import CurrentUser
from app.models.procurement import PurchaseRequestItem
from app.repositories.procurement import ProcurementRepository
from app.schemas.recommendations_v2 import (
    ProductRecommendationResponse,
    SelectedProductDTO,
    SupplierRecommendationResponse,
)
from app.services.permissions import require_any_role
from app.services.recommendation.api_mapper import map_product_result, map_supplier_result
from app.services.recommendation.service import RecommendationCoreService
from app.services.recommendation.types import (
    MAX_PRODUCT_RECOMMENDATIONS,
    MAX_SUPPLIER_RECOMMENDATIONS,
    SelectedProductRef,
)


class RecommendationApiService:
    def __init__(
        self,
        core: RecommendationCoreService | None = None,
        procurement: ProcurementRepository | None = None,
    ) -> None:
        self.core = core or RecommendationCoreService()
        self.procurement = procurement or ProcurementRepository()

    async def _visible_item(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        request_item_id: int,
    ) -> PurchaseRequestItem:
        item = await self.procurement.get_request_item(session, request_item_id)
        if item is None or not item.is_active:
            raise AppError("REQUEST_ITEM_NOT_FOUND", "采购项不存在", 404)
        request = await self.procurement.get_request(session, item.request_id)
        if request is None:
            raise AppError("REQUEST_ITEM_NOT_FOUND", "采购项不存在", 404)
        visible = await self.procurement.can_view_request(
            session,
            request,
            current_user.employee_id,
            current_user.has_any_role(RoleCode.ADMIN.value),
            current_user.building_ids,
            current_user.has_any_role(RoleCode.BUILDING_MANAGER.value),
        )
        if not visible:
            raise AppError("PERMISSION_DENIED", "无权查看该采购项推荐", 403)
        return item

    async def products(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        request_item_id: int,
        *,
        top_k: int,
        now: datetime | None = None,
    ) -> ProductRecommendationResponse:
        require_any_role(
            current_user,
            RoleCode.APPLICANT.value,
            RoleCode.BUILDING_MANAGER.value,
            RoleCode.PURCHASER.value,
            RoleCode.ADMIN.value,
        )
        item = await self._visible_item(session, current_user, request_item_id)
        result = await self.core.recommend_products(
            session, request_item_id, limit=MAX_PRODUCT_RECOMMENDATIONS, now=now
        )
        response = map_product_result(result, item)
        response.recommendations = response.recommendations[:top_k]
        response.returned_count = len(response.recommendations)
        return response

    async def suppliers(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        request_item_id: int,
        *,
        selected_product: SelectedProductDTO | None,
        top_k: int,
        now: datetime | None = None,
    ) -> SupplierRecommendationResponse:
        require_any_role(
            current_user,
            RoleCode.BUILDING_MANAGER.value,
            RoleCode.PURCHASER.value,
            RoleCode.ADMIN.value,
        )
        item = await self._visible_item(session, current_user, request_item_id)
        selected = (
            SelectedProductRef(
                product_key=selected_product.product_key,
                equipment_category_id=selected_product.equipment_category_id,
                equipment_model_id=selected_product.equipment_model_id,
                item_name=selected_product.item_name,
                brand=selected_product.brand,
                model=selected_product.model,
            )
            if selected_product is not None
            else None
        )
        try:
            result = await self.core.recommend_suppliers(
                session,
                request_item_id,
                selected,
                limit=MAX_SUPPLIER_RECOMMENDATIONS,
                now=now,
            )
        except AppError as exc:
            if exc.code == "SELECTED_PRODUCT_REQUIRED":
                raise AppError(exc.code, exc.message, 422) from exc
            if exc.code == "SELECTED_PRODUCT_CATEGORY_MISMATCH":
                raise AppError("SELECTED_PRODUCT_MISMATCH", exc.message, 422) from exc
            raise
        response = map_supplier_result(result, item)
        response.recommendations = response.recommendations[:top_k]
        response.returned_count = len(response.recommendations)
        return response
