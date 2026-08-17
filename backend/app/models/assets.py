from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EquipmentCategory(Base):
    __tablename__ = "equipment_category"
    __table_args__ = (
        UniqueConstraint("category_code", name="uq_equipment_category_code"),
        Index("ix_equipment_category_parent", "parent_category_id"),
        Index("ix_equipment_category_status", "status"),
        CheckConstraint("category_level IN (1, 2, 3)", name="category_level_valid"),
    )

    category_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_category_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("equipment_category.category_id", ondelete="RESTRICT"),
        nullable=True,
    )
    category_code: Mapped[str] = mapped_column(String(50), nullable=False)
    category_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category_level: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EquipmentModel(Base):
    __tablename__ = "equipment_model"
    __table_args__ = (
        Index("ix_equipment_model_category", "category_id"),
        Index("ix_equipment_model_brand", "brand"),
        Index("ix_equipment_model_model", "model"),
        Index("ix_equipment_model_lifecycle", "lifecycle_status"),
    )

    model_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("equipment_category.category_id", ondelete="RESTRICT"),
        nullable=False,
    )
    brand: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model: Mapped[str] = mapped_column(String(150), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    specifications: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    default_unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Asset(Base):
    __tablename__ = "asset"
    __table_args__ = (
        UniqueConstraint("asset_code", name="uq_asset_code"),
        Index("ix_asset_name", "asset_name"),
        Index("ix_asset_category", "category_id"),
        Index("ix_asset_model", "model_id"),
        Index("ix_asset_building", "building_id"),
        Index("ix_asset_status", "status"),
        Index("ix_asset_criticality", "criticality"),
        Index("ix_asset_serial", "serial_number"),
        Index("ix_asset_redundancy_group", "redundancy_group"),
        Index("ix_asset_building_category", "building_id", "category_id"),
        CheckConstraint("version >= 0", name="version_non_negative"),
    )

    asset_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_code: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("equipment_category.category_id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("equipment_model.model_id", ondelete="RESTRICT"),
        nullable=True,
    )
    building_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("building.building_id", ondelete="RESTRICT"), nullable=False
    )
    location: Mapped[str | None] = mapped_column(String(250), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    criticality: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    commissioned_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    warranty_end_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    configuration: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    redundancy_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    redundancy_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AssetComponent(Base):
    __tablename__ = "asset_component"
    __table_args__ = (
        Index("ix_asset_component_asset", "asset_id"),
        Index("ix_asset_component_category", "component_category"),
        Index("ix_asset_component_part", "model_or_part_no"),
        Index("ix_asset_component_asset_category", "asset_id", "component_category"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    component_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("asset.asset_id", ondelete="RESTRICT"), nullable=False
    )
    component_name: Mapped[str] = mapped_column(String(150), nullable=False)
    component_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model_or_part_no: Mapped[str | None] = mapped_column(String(150), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, default=Decimal("1"), server_default=text("1.000")
    )
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="NORMAL")
    replaceable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AssetRelation(Base):
    __tablename__ = "asset_relation"
    __table_args__ = (
        UniqueConstraint(
            "source_asset_id", "relation_type", "target_asset_id", name="uq_asset_relation"
        ),
        Index("ix_asset_relation_source", "source_asset_id"),
        Index("ix_asset_relation_target", "target_asset_id"),
        Index("ix_asset_relation_type", "relation_type"),
        CheckConstraint("source_asset_id <> target_asset_id", name="different_assets"),
    )

    relation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_asset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("asset.asset_id", ondelete="RESTRICT"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_asset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("asset.asset_id", ondelete="RESTRICT"), nullable=False
    )
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
