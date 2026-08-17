from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AssetSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EquipmentCategoryData(AssetSchema):
    category_id: int
    parent_category_id: int | None
    category_code: str
    category_name: str
    category_level: int
    description: str | None
    sort_order: int
    status: str


class EquipmentCategoryListData(BaseModel):
    items: list[EquipmentCategoryData]


class EquipmentModelData(AssetSchema):
    model_id: int
    category_id: int
    brand: str | None
    model: str
    model_name: str | None
    specifications: dict | None
    default_unit: str | None
    lifecycle_status: str
    remark: str | None


class EquipmentModelListData(BaseModel):
    items: list[EquipmentModelData]
    page: int
    page_size: int
    total: int


class BuildingSummaryData(BaseModel):
    building_id: int
    building_name: str


class AssetData(AssetSchema):
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
    configuration: dict | None
    aliases: list[str] | None
    redundancy_group: str | None
    redundancy_mode: str | None
    remark: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class AssetSummaryData(AssetData):
    category: EquipmentCategoryData
    model: EquipmentModelData | None
    building: BuildingSummaryData


class AssetListData(BaseModel):
    items: list[AssetSummaryData]
    page: int
    page_size: int
    total: int


class AssetComponentData(AssetSchema):
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


class RelatedAssetData(BaseModel):
    asset_id: int
    asset_code: str
    asset_name: str
    building_id: int
    location: str | None
    status: str


class AssetRelationData(AssetSchema):
    relation_id: int
    source_asset_id: int
    relation_type: str
    target_asset_id: int
    remark: str | None
    status: str
    direction: str
    related_asset: RelatedAssetData


class AssetContextData(BaseModel):
    asset: AssetSummaryData
    components: list[AssetComponentData]
    relations: list[AssetRelationData]
    redundancy_peers: list[AssetSummaryData]
