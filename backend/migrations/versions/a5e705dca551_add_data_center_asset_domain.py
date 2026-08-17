"""add data center asset domain

Revision ID: a5e705dca551
Revises: 816575c8be0c
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "a5e705dca551"
down_revision: str | Sequence[str] | None = "816575c8be0c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "equipment_category",
        sa.Column("category_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("parent_category_id", sa.BigInteger(), nullable=True),
        sa.Column("category_code", sa.String(50), nullable=False),
        sa.Column("category_name", sa.String(100), nullable=False),
        sa.Column("category_level", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "category_level IN (1, 2, 3)", name=op.f("ck_equipment_category_category_level_valid")
        ),
        sa.ForeignKeyConstraint(
            ["parent_category_id"], ["equipment_category.category_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("category_id"),
        sa.UniqueConstraint("category_code", name="uq_equipment_category_code"),
    )
    op.create_index("ix_equipment_category_parent", "equipment_category", ["parent_category_id"])
    op.create_index("ix_equipment_category_status", "equipment_category", ["status"])
    op.create_table(
        "equipment_model",
        sa.Column("model_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("brand", sa.String(150), nullable=True),
        sa.Column("model", sa.String(150), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("specifications", mysql.JSON(), nullable=True),
        sa.Column("default_unit", sa.String(30), nullable=True),
        sa.Column("lifecycle_status", sa.String(30), nullable=False),
        sa.Column("remark", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"], ["equipment_category.category_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("model_id"),
    )
    for name, columns in (
        ("category", ["category_id"]),
        ("brand", ["brand"]),
        ("model", ["model"]),
        ("lifecycle", ["lifecycle_status"]),
    ):
        op.create_index(f"ix_equipment_model_{name}", "equipment_model", columns)
    op.create_table(
        "asset",
        sa.Column("asset_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asset_code", sa.String(100), nullable=False),
        sa.Column("asset_name", sa.String(200), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("model_id", sa.BigInteger(), nullable=True),
        sa.Column("building_id", sa.BigInteger(), nullable=False),
        sa.Column("location", sa.String(250), nullable=True),
        sa.Column("serial_number", sa.String(150), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("criticality", sa.String(20), nullable=False),
        sa.Column("commissioned_at", sa.Date(), nullable=True),
        sa.Column("warranty_end_at", sa.Date(), nullable=True),
        sa.Column("configuration", mysql.JSON(), nullable=True),
        sa.Column("aliases", mysql.JSON(), nullable=True),
        sa.Column("redundancy_group", sa.String(100), nullable=True),
        sa.Column("redundancy_mode", sa.String(30), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("version >= 0", name=op.f("ck_asset_version_non_negative")),
        sa.ForeignKeyConstraint(["building_id"], ["building.building_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["equipment_category.category_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["model_id"], ["equipment_model.model_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("asset_id"),
        sa.UniqueConstraint("asset_code", name="uq_asset_code"),
    )
    for name, columns in (
        ("name", ["asset_name"]),
        ("category", ["category_id"]),
        ("model", ["model_id"]),
        ("building", ["building_id"]),
        ("status", ["status"]),
        ("criticality", ["criticality"]),
        ("serial", ["serial_number"]),
        ("redundancy_group", ["redundancy_group"]),
        ("building_category", ["building_id", "category_id"]),
    ):
        op.create_index(f"ix_asset_{name}", "asset", columns)
    op.create_table(
        "asset_component",
        sa.Column("component_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("component_name", sa.String(150), nullable=False),
        sa.Column("component_category", sa.String(100), nullable=True),
        sa.Column("brand", sa.String(150), nullable=True),
        sa.Column("model_or_part_no", sa.String(150), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 3), server_default=sa.text("1.000"), nullable=False),
        sa.Column("unit", sa.String(30), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("replaceable", sa.Boolean(), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_asset_component_quantity_positive")),
        sa.ForeignKeyConstraint(["asset_id"], ["asset.asset_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("component_id"),
    )
    for name, columns in (
        ("asset", ["asset_id"]),
        ("category", ["component_category"]),
        ("part", ["model_or_part_no"]),
        ("asset_category", ["asset_id", "component_category"]),
    ):
        op.create_index(f"ix_asset_component_{name}", "asset_component", columns)
    op.create_table(
        "asset_relation",
        sa.Column("relation_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_asset_id", sa.BigInteger(), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("target_asset_id", sa.BigInteger(), nullable=False),
        sa.Column("remark", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "source_asset_id <> target_asset_id", name=op.f("ck_asset_relation_different_assets")
        ),
        sa.ForeignKeyConstraint(["source_asset_id"], ["asset.asset_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_asset_id"], ["asset.asset_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("relation_id"),
        sa.UniqueConstraint(
            "source_asset_id", "relation_type", "target_asset_id", name="uq_asset_relation"
        ),
    )
    for name, columns in (
        ("source", ["source_asset_id"]),
        ("target", ["target_asset_id"]),
        ("type", ["relation_type"]),
    ):
        op.create_index(f"ix_asset_relation_{name}", "asset_relation", columns)


def downgrade() -> None:
    op.drop_table("asset_relation")
    op.drop_table("asset_component")
    op.drop_table("asset")
    op.drop_table("equipment_model")
    op.drop_table("equipment_category")
