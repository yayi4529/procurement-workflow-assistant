from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity import CurrentUser
from app.models.assets import (
    Asset,
    AssetComponent,
    AssetRelation,
    EquipmentCategory,
    EquipmentModel,
)
from app.models.identity import Building


class AssetRepository:
    @staticmethod
    def visibility_condition(user: CurrentUser):
        return None if user.has_any_role("ADMIN") else Asset.building_id.in_(user.building_ids)

    async def list_categories(
        self,
        session: AsyncSession,
        *,
        parent_category_id: int | None,
        category_level: int | None,
        status: str | None,
    ) -> list[EquipmentCategory]:
        conditions = []
        if parent_category_id is not None:
            conditions.append(EquipmentCategory.parent_category_id == parent_category_id)
        if category_level is not None:
            conditions.append(EquipmentCategory.category_level == category_level)
        if status:
            conditions.append(EquipmentCategory.status == status)
        result = await session.scalars(
            select(EquipmentCategory)
            .where(*conditions)
            .order_by(EquipmentCategory.sort_order, EquipmentCategory.category_id)
        )
        return list(result)

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
    ) -> tuple[list[EquipmentModel], int]:
        conditions = []
        if category_id is not None:
            conditions.append(EquipmentModel.category_id == category_id)
        if brand:
            conditions.append(EquipmentModel.brand.like(f"%{brand}%"))
        if q:
            conditions.append(
                or_(
                    EquipmentModel.model.like(f"%{q}%"),
                    EquipmentModel.model_name.like(f"%{q}%"),
                    EquipmentModel.brand.like(f"%{q}%"),
                )
            )
        if lifecycle_status:
            conditions.append(EquipmentModel.lifecycle_status == lifecycle_status)
        base = select(EquipmentModel).where(*conditions)
        total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = await session.scalars(
            base.order_by(EquipmentModel.model_id).offset((page - 1) * page_size).limit(page_size)
        )
        return list(rows), total

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
    ) -> tuple[list[tuple[Asset, EquipmentCategory, EquipmentModel | None, Building]], int]:
        conditions = []
        visibility = self.visibility_condition(user)
        if visibility is not None:
            conditions.append(visibility)
        if building_id is not None:
            conditions.append(Asset.building_id == building_id)
        if category_id is not None:
            conditions.append(Asset.category_id == category_id)
        if category_code:
            conditions.append(EquipmentCategory.category_code == category_code)
        if model_id is not None:
            conditions.append(Asset.model_id == model_id)
        if status:
            conditions.append(Asset.status == status)
        if criticality:
            conditions.append(Asset.criticality == criticality)
        if q:
            pattern = f"%{q}%"
            conditions.append(
                or_(
                    Asset.asset_code.like(pattern),
                    Asset.asset_name.like(pattern),
                    Asset.serial_number.like(pattern),
                    cast(Asset.aliases, String).like(pattern),
                    Asset.location.like(pattern),
                )
            )
        base = (
            select(Asset, EquipmentCategory, EquipmentModel, Building)
            .join(EquipmentCategory, EquipmentCategory.category_id == Asset.category_id)
            .outerjoin(EquipmentModel, EquipmentModel.model_id == Asset.model_id)
            .join(Building, Building.building_id == Asset.building_id)
            .where(*conditions)
        )
        total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)
        result = await session.execute(
            base.order_by(Asset.asset_id).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.tuples()), total

    async def get_asset(
        self, session: AsyncSession, user: CurrentUser, asset_id: int
    ) -> tuple[Asset, EquipmentCategory, EquipmentModel | None, Building] | None:
        conditions = [Asset.asset_id == asset_id]
        visibility = self.visibility_condition(user)
        if visibility is not None:
            conditions.append(visibility)
        result = await session.execute(
            select(Asset, EquipmentCategory, EquipmentModel, Building)
            .join(EquipmentCategory, EquipmentCategory.category_id == Asset.category_id)
            .outerjoin(EquipmentModel, EquipmentModel.model_id == Asset.model_id)
            .join(Building, Building.building_id == Asset.building_id)
            .where(*conditions)
        )
        return result.tuples().one_or_none()

    async def context(
        self, session: AsyncSession, asset: Asset
    ) -> tuple[
        list[AssetComponent],
        list[tuple[AssetRelation, Asset, str]],
        list[tuple[Asset, EquipmentCategory, EquipmentModel | None, Building]],
    ]:
        components = list(
            await session.scalars(
                select(AssetComponent)
                .where(AssetComponent.asset_id == asset.asset_id)
                .order_by(AssetComponent.component_id)
            )
        )
        relation_rows = await session.execute(
            select(AssetRelation)
            .where(
                or_(
                    AssetRelation.source_asset_id == asset.asset_id,
                    AssetRelation.target_asset_id == asset.asset_id,
                ),
                AssetRelation.status == "ACTIVE",
            )
            .order_by(AssetRelation.relation_id)
        )
        relations = list(relation_rows.scalars())
        related_ids = {
            r.target_asset_id if r.source_asset_id == asset.asset_id else r.source_asset_id
            for r in relations
        }
        related_map: dict[int, Asset] = {}
        if related_ids:
            related_map = {
                item.asset_id: item
                for item in await session.scalars(
                    select(Asset).where(Asset.asset_id.in_(related_ids))
                )
            }
        enriched = [
            (
                r,
                related_map[
                    r.target_asset_id if r.source_asset_id == asset.asset_id else r.source_asset_id
                ],
                "OUTGOING" if r.source_asset_id == asset.asset_id else "INCOMING",
            )
            for r in relations
        ]
        peers: list[tuple[Asset, EquipmentCategory, EquipmentModel | None, Building]] = []
        if asset.redundancy_group:
            peer_rows = await session.execute(
                select(Asset, EquipmentCategory, EquipmentModel, Building)
                .join(EquipmentCategory, EquipmentCategory.category_id == Asset.category_id)
                .outerjoin(EquipmentModel, EquipmentModel.model_id == Asset.model_id)
                .join(Building, Building.building_id == Asset.building_id)
                .where(
                    Asset.redundancy_group == asset.redundancy_group,
                    Asset.asset_id != asset.asset_id,
                )
                .order_by(Asset.asset_id)
            )
            peers = list(peer_rows.tuples())
        return components, enriched, peers
