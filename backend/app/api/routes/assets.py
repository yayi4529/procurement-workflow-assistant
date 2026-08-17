from fastapi import APIRouter, Query

from app.api.dependencies import CurrentUserDependency, DbSession
from app.core.responses import ApiResponse
from app.schemas.assets import (
    AssetContextData,
    AssetListData,
    AssetSummaryData,
    EquipmentCategoryListData,
    EquipmentModelListData,
)
from app.services.assets import AssetQueryService

router = APIRouter(tags=["assets"])


@router.get("/api/v1/equipment/categories", response_model=ApiResponse[EquipmentCategoryListData])
async def list_equipment_categories(
    current_user: CurrentUserDependency,
    session: DbSession,
    parent_category_id: int | None = Query(default=None, gt=0),
    category_level: int | None = Query(default=None),
    status: str | None = Query(default="ACTIVE"),
) -> ApiResponse[EquipmentCategoryListData]:
    del current_user
    data = await AssetQueryService().list_categories(
        session, parent_category_id=parent_category_id, category_level=category_level, status=status
    )
    return ApiResponse(data=data)


@router.get("/api/v1/equipment/models", response_model=ApiResponse[EquipmentModelListData])
async def list_equipment_models(
    current_user: CurrentUserDependency,
    session: DbSession,
    category_id: int | None = Query(default=None, gt=0),
    brand: str | None = Query(default=None, max_length=150),
    q: str | None = Query(default=None, max_length=200),
    lifecycle_status: str | None = Query(default="ACTIVE"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[EquipmentModelListData]:
    del current_user
    data = await AssetQueryService().list_models(
        session,
        category_id=category_id,
        brand=brand,
        q=q,
        lifecycle_status=lifecycle_status,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(data=data)


@router.get("/api/v1/assets", response_model=ApiResponse[AssetListData])
async def search_assets(
    current_user: CurrentUserDependency,
    session: DbSession,
    building_id: int | None = Query(default=None, gt=0),
    category_id: int | None = Query(default=None, gt=0),
    category_code: str | None = Query(default=None, max_length=50),
    model_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default="ACTIVE"),
    criticality: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=250),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[AssetListData]:
    data = await AssetQueryService().search_assets(
        session,
        current_user,
        building_id=building_id,
        category_id=category_id,
        category_code=category_code,
        model_id=model_id,
        status=status,
        criticality=criticality,
        q=q,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(data=data)


@router.get("/api/v1/assets/{asset_id}", response_model=ApiResponse[AssetSummaryData])
async def get_asset(
    asset_id: int, current_user: CurrentUserDependency, session: DbSession
) -> ApiResponse[AssetSummaryData]:
    return ApiResponse(data=await AssetQueryService().get_asset(session, current_user, asset_id))


@router.get("/api/v1/assets/{asset_id}/context", response_model=ApiResponse[AssetContextData])
async def get_asset_context(
    asset_id: int, current_user: CurrentUserDependency, session: DbSession
) -> ApiResponse[AssetContextData]:
    return ApiResponse(data=await AssetQueryService().get_context(session, current_user, asset_id))
