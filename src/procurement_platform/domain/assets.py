from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from procurement_platform.domain.json_types import JsonObject


class AssetDomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EquipmentCategorySummary(AssetDomainModel):
    category_id: int
    parent_category_id: int | None
    category_code: str
    category_name: str
    category_level: int
    description: str | None
    sort_order: int
    status: str


class EquipmentModelSummary(AssetDomainModel):
    model_id: int
    category_id: int
    brand: str | None
    model: str
    model_name: str | None
    specifications: JsonObject | None
    default_unit: str | None
    lifecycle_status: str
    remark: str | None


class BuildingSummary(AssetDomainModel):
    building_id: int
    building_name: str


class AssetSummary(AssetDomainModel):
    asset_id: int
    asset_code: str
    asset_name: str
    category_id: int
    model_id: int | None
    building_id: int
    location: str | None
    serial_number: str | None
    status: str
    criticality: str
    commissioned_at: date | None
    warranty_end_at: date | None
    configuration: JsonObject | None
    aliases: tuple[str, ...]
    redundancy_group: str | None
    redundancy_mode: str | None
    remark: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    category: EquipmentCategorySummary
    model: EquipmentModelSummary | None
    building: BuildingSummary


class AssetComponent(AssetDomainModel):
    component_id: int
    asset_id: int
    component_name: str
    component_category: str | None
    brand: str | None
    model_or_part_no: str | None
    quantity: Decimal
    unit: str | None
    status: str
    replaceable: bool
    remark: str | None


class RelatedAsset(AssetDomainModel):
    asset_id: int
    asset_code: str
    asset_name: str
    building_id: int
    location: str | None
    status: str


class AssetRelation(AssetDomainModel):
    relation_id: int
    source_asset_id: int
    relation_type: str
    target_asset_id: int
    remark: str | None
    status: str
    direction: str
    related_asset: RelatedAsset


class AssetContext(AssetDomainModel):
    asset: AssetSummary
    components: tuple[AssetComponent, ...]
    relations: tuple[AssetRelation, ...]
    redundancy_peers: tuple[AssetSummary, ...]


class AssetPage(AssetDomainModel):
    items: tuple[AssetSummary, ...]
    page: int
    page_size: int
    total: int


class EquipmentModelPage(AssetDomainModel):
    items: tuple[EquipmentModelSummary, ...]
    page: int
    page_size: int
    total: int
