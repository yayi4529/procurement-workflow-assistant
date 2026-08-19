from fastapi import APIRouter, Query

from app.api.dependencies import CurrentUserDependency, DbSession
from app.core.responses import ApiResponse
from app.schemas.recommendations import (
    ProductRecommendationData,
    PurchaseHistoryRecommendationData,
    SupplierRecommendationData,
)
from app.schemas.recommendations_v2 import (
    ProductRecommendationResponse,
    SupplierRecommendationRequest,
    SupplierRecommendationResponse,
)
from app.services.recommendation.api_service import RecommendationApiService
from app.services.recommendations import RecommendationService

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


@router.get(
    "/items/{request_item_id}/products",
    response_model=ApiResponse[ProductRecommendationResponse],
    responses={404: {"description": "REQUEST_ITEM_NOT_FOUND"}},
)
async def recommend_item_products(
    current_user: CurrentUserDependency,
    session: DbSession,
    request_item_id: int,
    top_k: int = Query(default=10, ge=1, le=10),
) -> ApiResponse[ProductRecommendationResponse]:
    data = await RecommendationApiService().products(
        session,
        current_user,
        request_item_id,
        top_k=top_k,
    )
    return ApiResponse(data=data)


@router.post(
    "/items/{request_item_id}/suppliers",
    response_model=ApiResponse[SupplierRecommendationResponse],
    responses={
        404: {"description": "REQUEST_ITEM_NOT_FOUND"},
        422: {"description": "Validation error or selected product required/mismatch"},
    },
)
async def recommend_item_suppliers(
    current_user: CurrentUserDependency,
    session: DbSession,
    request_item_id: int,
    payload: SupplierRecommendationRequest,
) -> ApiResponse[SupplierRecommendationResponse]:
    data = await RecommendationApiService().suppliers(
        session,
        current_user,
        request_item_id,
        selected_product=payload.selected_product,
        top_k=payload.top_k,
    )
    return ApiResponse(data=data)


@router.get("/products", response_model=ApiResponse[ProductRecommendationData])
async def recommend_products(
    current_user: CurrentUserDependency,
    session: DbSession,
    device_name: str = Query(min_length=1),
    device_profession: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=30),
) -> ApiResponse[ProductRecommendationData]:
    data = await RecommendationService().products(
        session,
        current_user,
        device_profession=device_profession,
        device_name=device_name,
        keyword=keyword,
        limit=limit,
    )
    return ApiResponse(data=data)


@router.get(
    "/purchase-history",
    response_model=ApiResponse[PurchaseHistoryRecommendationData],
)
async def recommend_purchase_history(
    current_user: CurrentUserDependency,
    session: DbSession,
    requirement_id: int = Query(),
    limit: int = Query(default=10, ge=1, le=30),
) -> ApiResponse[PurchaseHistoryRecommendationData]:
    data = await RecommendationService().purchase_history(
        session,
        current_user,
        requirement_id=requirement_id,
        limit=limit,
    )
    return ApiResponse(data=data)


@router.get("/suppliers", response_model=ApiResponse[SupplierRecommendationData])
async def recommend_suppliers(
    current_user: CurrentUserDependency,
    session: DbSession,
    requirement_id: int = Query(),
    limit: int = Query(default=10, ge=1, le=30),
) -> ApiResponse[SupplierRecommendationData]:
    data = await RecommendationService().suppliers_for_request(
        session,
        current_user,
        requirement_id=requirement_id,
        limit=limit,
    )
    return ApiResponse(data=data)
