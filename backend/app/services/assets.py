from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.domain.enums import AssetCriticality, AssetStatus
from app.domain.identity import CurrentUser
from app.models.assets import (
    Asset,
    AssetRelation,
    EquipmentCategory,
    EquipmentModel,
)
from app.models.identity import Building
from app.repositories.assets import AssetRepository
from app.schemas.assets import (
    AssetComponentData,
    AssetContextData,
    AssetData,
    AssetListData,
    AssetRelationData,
    AssetSummaryData,
    BuildingSummaryData,
    EquipmentCategoryData,
    EquipmentCategoryListData,
    EquipmentModelData,
    EquipmentModelListData,
    RelatedAssetData,
)


class AssetQueryService:
    def __init__(self, repository: AssetRepository | None = None) -> None:
        self.repository = repository or AssetRepository()

    @staticmethod
    def validate_asset_model_category(
        *, asset_category_id: int, model: EquipmentModel | None
    ) -> None:
        if model is not None and model.category_id != asset_category_id:
            raise AppError("ASSET_MODEL_CATEGORY_MISMATCH", "资产类别与设备型号类别不一致", 400)

    @staticmethod
    def validate_relation(
        *, source_asset_id: int, target_asset_id: int, relation_type: str
    ) -> None:
        from app.domain.enums import AssetRelationType

        if source_asset_id == target_asset_id:
            raise AppError("ASSET_RELATION_SELF_REFERENCE", "资产不能关联自身", 400)
        if relation_type not in {item.value for item in AssetRelationType}:
            raise AppError("VALIDATION_ERROR", "资产关系类型无效", 400)

    @staticmethod
    def _category(value: EquipmentCategory) -> EquipmentCategoryData:
        return EquipmentCategoryData.model_validate(value)

    @staticmethod
    def _model(value: EquipmentModel | None) -> EquipmentModelData | None:
        return EquipmentModelData.model_validate(value) if value is not None else None

    def _asset_summary(
        self, row: tuple[Asset, EquipmentCategory, EquipmentModel | None, Building]
    ) -> AssetSummaryData:
        asset, category, model, building = row
        return AssetSummaryData(
            **AssetData.model_validate(asset).model_dump(),
            category=self._category(category),
            model=self._model(model),
            building=BuildingSummaryData(
                building_id=building.building_id, building_name=building.building_name
            ),
        )

    async def list_categories(
        self,
        session: AsyncSession,
        *,
        parent_category_id: int | None,
        category_level: int | None,
        status: str | None,
    ) -> EquipmentCategoryListData:
        if category_level is not None and category_level not in {1, 2, 3}:
            raise AppError("VALIDATION_ERROR", "category_level 无效", 400)
        normalized = status.upper() if status else None
        if normalized not in {None, "ACTIVE", "INACTIVE"}:
            raise AppError("VALIDATION_ERROR", "分类状态筛选值无效", 400)
        rows = await self.repository.list_categories(
            session,
            parent_category_id=parent_category_id,
            category_level=category_level,
            status=normalized,
        )
        return EquipmentCategoryListData(items=[self._category(row) for row in rows])

    async def list_models(
        self,
        session: AsyncSession,
        *,
        category_id: int | None,
        brand: str | None,
        q: str | None,
        lifecycle_status: str | None,
        page: int,
        page_size: int,
    ) -> EquipmentModelListData:
        normalized = lifecycle_status.upper() if lifecycle_status else None
        if normalized not in {None, "ACTIVE", "DISCONTINUED", "OBSOLETE"}:
            raise AppError("VALIDATION_ERROR", "型号生命周期筛选值无效", 400)
        rows, total = await self.repository.list_models(
            session,
            category_id=category_id,
            brand=brand,
            q=q,
            lifecycle_status=normalized,
            page=page,
            page_size=page_size,
        )
        return EquipmentModelListData(
            items=[EquipmentModelData.model_validate(row) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def search_assets(
        self,
        session: AsyncSession,
        user: CurrentUser,
        *,
        building_id: int | None,
        category_id: int | None,
        category_code: str | None,
        model_id: int | None,
        status: str | None,
        criticality: str | None,
        q: str | None,
        page: int,
        page_size: int,
    ) -> AssetListData:
        normalized_status = status.upper() if status else None
        normalized_criticality = criticality.upper() if criticality else None
        if normalized_status and normalized_status not in {item.value for item in AssetStatus}:
            raise AppError("VALIDATION_ERROR", "资产状态筛选值无效", 400)
        if normalized_criticality and normalized_criticality not in {
            item.value for item in AssetCriticality
        }:
            raise AppError("VALIDATION_ERROR", "资产重要等级筛选值无效", 400)
        if building_id is not None and not user.belongs_to_building(building_id):
            raise AppError("BUILDING_NOT_ALLOWED", "当前用户无权访问该楼宇资产", 403)
        rows, total = await self.repository.search_assets(
            session,
            user,
            building_id=building_id,
            category_id=category_id,
            category_code=category_code.upper() if category_code else None,
            model_id=model_id,
            status=normalized_status,
            criticality=normalized_criticality,
            q=q,
            page=page,
            page_size=page_size,
        )
        return AssetListData(
            items=[self._asset_summary(row) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def get_asset(
        self, session: AsyncSession, user: CurrentUser, asset_id: int
    ) -> AssetSummaryData:
        row = await self.repository.get_asset(session, user, asset_id)
        if row is None:
            raise AppError("ASSET_NOT_FOUND", "资产不存在或不可见", 404)
        return self._asset_summary(row)

    async def get_context(
        self, session: AsyncSession, user: CurrentUser, asset_id: int
    ) -> AssetContextData:
        row = await self.repository.get_asset(session, user, asset_id)
        if row is None:
            raise AppError("ASSET_NOT_FOUND", "资产不存在或不可见", 404)
        asset = row[0]
        components, relations, peers = await self.repository.context(session, asset)
        return AssetContextData(
            asset=self._asset_summary(row),
            components=[AssetComponentData.model_validate(item) for item in components],
            relations=[self._relation(item) for item in relations],
            redundancy_peers=[
                self._asset_summary(peer)
                for peer in peers
                if user.belongs_to_building(peer[0].building_id)
            ],
        )

    @staticmethod
    def _relation(row: tuple[AssetRelation, Asset, str]) -> AssetRelationData:
        relation, related, direction = row
        return AssetRelationData(
            relation_id=relation.relation_id,
            source_asset_id=relation.source_asset_id,
            relation_type=relation.relation_type,
            target_asset_id=relation.target_asset_id,
            remark=relation.remark,
            status=relation.status,
            direction=direction,
            related_asset=RelatedAssetData(
                asset_id=related.asset_id,
                asset_code=related.asset_code,
                asset_name=related.asset_name,
                building_id=related.building_id,
                location=related.location,
                status=related.status,
            ),
        )
