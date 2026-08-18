"""expand Task06 multi-item schema and backfill legacy rows

Revision ID: b6f11c06a001
Revises: a5e705dca551
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "b6f11c06a001"
down_revision: str | Sequence[str] | None = "a5e705dca551"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _scalar(sql: str) -> object:
    if context.is_offline_mode():
        op.execute(sa.text(sql))
        return None
    return op.get_bind().execute(sa.text(sql)).scalar()


def upgrade() -> None:
    op.add_column("purchase_request", sa.Column("source_asset_id", sa.BigInteger(), nullable=True))
    op.add_column("purchase_request", sa.Column("request_type", sa.String(30), nullable=True))
    op.create_foreign_key(
        "fk_purchase_request_source_asset_id_asset",
        "purchase_request",
        "asset",
        ["source_asset_id"],
        ["asset_id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_purchase_request_source_asset_id", "purchase_request", ["source_asset_id"])
    op.create_index("ix_purchase_request_request_type", "purchase_request", ["request_type"])
    op.drop_constraint(
        op.f("ck_purchase_request_quantity_positive"), "purchase_request", type_="check"
    )

    op.create_table(
        "purchase_request_item",
        sa.Column("request_item_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.BigInteger(), nullable=False),
        sa.Column("item_no", sa.Integer(), nullable=False),
        sa.Column("item_kind", sa.String(30), nullable=False),
        sa.Column("equipment_category_id", sa.BigInteger(), nullable=True),
        sa.Column("equipment_model_id", sa.BigInteger(), nullable=True),
        sa.Column("item_name", sa.String(200), nullable=False),
        sa.Column("brand_snapshot", sa.String(150), nullable=True),
        sa.Column("model_snapshot", sa.String(150), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("requires_warehouse", sa.Boolean(), nullable=False),
        sa.Column("item_reason", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("item_no > 0", name="request_item_no_positive"),
        sa.CheckConstraint("quantity > 0", name="request_item_quantity_positive"),
        sa.ForeignKeyConstraint(
            ["request_id"], ["purchase_request.request_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["equipment_category_id"], ["equipment_category.category_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["equipment_model_id"], ["equipment_model.model_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("request_item_id"),
        sa.UniqueConstraint("request_id", "item_no", name="uq_purchase_request_item_no"),
    )
    for name, columns in (
        ("request_id", ["request_id"]),
        ("request_active", ["request_id", "is_active"]),
        ("kind", ["item_kind"]),
        ("category_id", ["equipment_category_id"]),
        ("model_id", ["equipment_model_id"]),
    ):
        op.create_index(f"ix_purchase_request_item_{name}", "purchase_request_item", columns)

    op.create_table(
        "purchase_review_item",
        sa.Column("review_item_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("review_id", sa.BigInteger(), nullable=False),
        sa.Column("request_item_id", sa.BigInteger(), nullable=False),
        sa.Column("item_kind_snapshot", sa.String(30), nullable=False),
        sa.Column("item_name_snapshot", sa.String(200), nullable=False),
        sa.Column("quantity_snapshot", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_snapshot", sa.String(30), nullable=False),
        sa.Column("brand_snapshot", sa.String(150), nullable=True),
        sa.Column("model_snapshot", sa.String(150), nullable=True),
        sa.Column("proposed_supplier_id", sa.BigInteger(), nullable=True),
        sa.Column("proposed_supplier_name_snapshot", sa.String(200), nullable=True),
        sa.Column("supplier_contact_name", sa.String(100), nullable=True),
        sa.Column("supplier_contact_info", sa.String(255), nullable=True),
        sa.Column("supplier_link", sa.String(1000), nullable=True),
        sa.Column("estimated_unit_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("estimated_total_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("need_contract", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("contract_type", sa.String(100), nullable=True),
        sa.Column("payment_method", sa.String(100), nullable=True),
        sa.Column("expected_arrival_date", sa.Date(), nullable=True),
        sa.Column("warranty_info", sa.String(255), nullable=True),
        sa.Column("item_remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity_snapshot > 0", name="review_item_quantity_positive"),
        sa.CheckConstraint(
            "estimated_unit_price IS NULL OR estimated_unit_price >= 0",
            name="review_item_unit_price_non_negative",
        ),
        sa.CheckConstraint(
            "estimated_total_price IS NULL OR estimated_total_price >= 0",
            name="review_item_total_price_non_negative",
        ),
        sa.ForeignKeyConstraint(["review_id"], ["purchase_review.review_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["request_item_id"], ["purchase_request_item.request_item_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["proposed_supplier_id"], ["supplier.supplier_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("review_item_id"),
        sa.UniqueConstraint("review_id", "request_item_id", name="uq_purchase_review_item"),
    )
    op.create_index("ix_purchase_review_item_review_id", "purchase_review_item", ["review_id"])
    op.create_index(
        "ix_purchase_review_item_request_item_id", "purchase_review_item", ["request_item_id"]
    )
    op.create_index(
        "ix_purchase_review_item_supplier_id", "purchase_review_item", ["proposed_supplier_id"]
    )

    op.add_column(
        "purchase_execution", sa.Column("request_item_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "purchase_execution", sa.Column("purchased_quantity", sa.Numeric(18, 3), nullable=True)
    )
    op.add_column("warehouse_receipt", sa.Column("execution_id", sa.BigInteger(), nullable=True))

    invalid = _scalar("""
        SELECT GROUP_CONCAT(request_id ORDER BY request_id)
        FROM purchase_request
        WHERE status NOT IN ('DRAFT', 'REJECTED')
          AND (device_name IS NULL OR TRIM(device_name) = '' OR quantity IS NULL OR quantity <= 0
               OR unit IS NULL OR TRIM(unit) = '')
    """)
    if invalid:
        raise RuntimeError(f"Task06 backfill cannot construct Item #1 for request_ids: {invalid}")

    op.execute(sa.text("UPDATE purchase_request SET request_type = 'PURCHASE'"))
    op.execute(
        sa.text("""
        INSERT INTO purchase_request_item
            (request_id, item_no, item_kind, item_name, brand_snapshot, model_snapshot,
             quantity, unit, requires_warehouse, is_active, created_at, updated_at)
        SELECT request_id, 1, 'EQUIPMENT', TRIM(device_name), brand, model,
               quantity, TRIM(unit), 1, 1, created_at, updated_at
        FROM purchase_request
        WHERE device_name IS NOT NULL AND TRIM(device_name) <> ''
          AND quantity IS NOT NULL AND quantity > 0 AND unit IS NOT NULL AND TRIM(unit) <> ''
    """)
    )
    op.execute(
        sa.text("""
        INSERT INTO purchase_review_item
            (review_id, request_item_id, item_kind_snapshot, item_name_snapshot,
             quantity_snapshot, unit_snapshot, brand_snapshot, model_snapshot,
             proposed_supplier_id, proposed_supplier_name_snapshot, supplier_contact_name,
             supplier_contact_info, supplier_link, estimated_unit_price, estimated_total_price,
             need_contract, contract_type, payment_method, expected_arrival_date, warranty_info,
             item_remark, created_at)
        SELECT r.review_id, i.request_item_id, i.item_kind, i.item_name, i.quantity, i.unit,
               i.brand_snapshot, i.model_snapshot, r.proposed_supplier_id, r.proposed_supplier_name,
               r.supplier_contact_name, r.supplier_contact_info, r.supplier_link,
               r.estimated_unit_price, r.estimated_total_price, r.need_contract, r.contract_type,
               r.payment_method, r.expected_arrival_date, r.warranty_info, r.review_remark, NOW()
        FROM purchase_review r JOIN purchase_request_item i
          ON i.request_id = r.request_id AND i.item_no = 1
    """)
    )
    op.execute(
        sa.text("""
        UPDATE purchase_execution e JOIN purchase_request_item i
          ON i.request_id = e.request_id AND i.item_no = 1
        SET e.request_item_id = i.request_item_id, e.purchased_quantity = i.quantity
    """)
    )
    orphan_receipts = _scalar("""
        SELECT GROUP_CONCAT(w.receipt_id ORDER BY w.receipt_id)
        FROM warehouse_receipt w LEFT JOIN purchase_execution e ON e.request_id = w.request_id
        WHERE e.execution_id IS NULL
    """)
    if orphan_receipts:
        raise RuntimeError(
            f"Task06 receipt backfill found receipts without execution: {orphan_receipts}"
        )
    op.execute(
        sa.text("""
        UPDATE warehouse_receipt w JOIN purchase_execution e ON e.request_id = w.request_id
        SET w.execution_id = e.execution_id
    """)
    )
    invalid_receipts = _scalar("""
        SELECT GROUP_CONCAT(w.receipt_id ORDER BY w.receipt_id)
        FROM warehouse_receipt w JOIN purchase_execution e ON e.execution_id = w.execution_id
        WHERE w.received_quantity <= 0 OR w.received_quantity > e.purchased_quantity
    """)
    if invalid_receipts:
        raise RuntimeError(
            f"Task06 receipt quantities violate execution totals: {invalid_receipts}"
        )


def downgrade() -> None:
    op.drop_column("warehouse_receipt", "execution_id")
    op.drop_column("purchase_execution", "purchased_quantity")
    op.drop_column("purchase_execution", "request_item_id")
    op.drop_table("purchase_review_item")
    op.drop_table("purchase_request_item")
    op.create_check_constraint("quantity_positive", "purchase_request", "quantity > 0")
    op.drop_index("ix_purchase_request_request_type", table_name="purchase_request")
    op.drop_index("ix_purchase_request_source_asset_id", table_name="purchase_request")
    op.drop_constraint(
        "fk_purchase_request_source_asset_id_asset", "purchase_request", type_="foreignkey"
    )
    op.drop_column("purchase_request", "request_type")
    op.drop_column("purchase_request", "source_asset_id")
