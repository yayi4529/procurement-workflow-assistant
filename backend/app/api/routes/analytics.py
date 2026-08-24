from fastapi import APIRouter

from app.api.dependencies import CurrentUserDependency, DbSession
from app.core.responses import ApiResponse
from app.db.session import analytics_engine
from app.schemas.analytics import AnalyticsCatalogData, AnalyticsQueryData, AnalyticsQueryRequest
from app.services.analytics import AnalyticsQueryService

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/catalog", response_model=ApiResponse[AnalyticsCatalogData])
async def get_analytics_catalog(
    current_user: CurrentUserDependency,
) -> ApiResponse[AnalyticsCatalogData]:
    return ApiResponse(data=AnalyticsQueryService(analytics_engine).catalog(current_user))


@router.post("/query", response_model=ApiResponse[AnalyticsQueryData])
async def run_analytics_query(
    payload: AnalyticsQueryRequest,
    current_user: CurrentUserDependency,
    session: DbSession,
) -> ApiResponse[AnalyticsQueryData]:
    data = await AnalyticsQueryService(analytics_engine).query(session, current_user, payload)
    return ApiResponse(data=data)
