"""constrain Task06 multi-item schema

Revision ID: b6f11c06a002
Revises: b6f11c06a001
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "b6f11c06a002"
down_revision: str | Sequence[str] | None = "b6f11c06a001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    checks = {
        "purchase executions without Item #1": (
            "SELECT COUNT(*) FROM purchase_execution "
            "WHERE request_item_id IS NULL OR purchased_quantity IS NULL"
        ),
        "warehouse receipts without execution": (
            "SELECT COUNT(*) FROM warehouse_receipt WHERE execution_id IS NULL"
        ),
    }
    for label, sql in checks.items():
        if not context.is_offline_mode() and bind.execute(sa.text(sql)).scalar():
            raise RuntimeError(f"Task06 constrain preflight failed: {label}")

    op.alter_column("purchase_request", "request_type", existing_type=sa.String(30), nullable=False)
    op.alter_column(
        "purchase_execution", "request_item_id", existing_type=sa.BigInteger(), nullable=False
    )
    op.alter_column(
        "purchase_execution", "purchased_quantity", existing_type=sa.Numeric(18, 3), nullable=False
    )
    op.alter_column(
        "warehouse_receipt", "execution_id", existing_type=sa.BigInteger(), nullable=False
    )
    op.create_index("ix_purchase_execution_request_id", "purchase_execution", ["request_id"])
    op.drop_constraint("uq_purchase_execution_request_id", "purchase_execution", type_="unique")
    op.create_unique_constraint(
        "uq_purchase_execution_request_item_id", "purchase_execution", ["request_item_id"]
    )
    op.create_foreign_key(
        "fk_purchase_execution_request_item_id_purchase_request_item",
        "purchase_execution",
        "purchase_request_item",
        ["request_item_id"],
        ["request_item_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "purchased_quantity_positive",
        "purchase_execution",
        "purchased_quantity > 0",
    )
    op.create_index("ix_warehouse_receipt_request_id", "warehouse_receipt", ["request_id"])
    op.drop_constraint("uq_warehouse_receipt_request_id", "warehouse_receipt", type_="unique")
    op.create_index("ix_warehouse_receipt_execution_id", "warehouse_receipt", ["execution_id"])
    op.create_foreign_key(
        "fk_warehouse_receipt_execution_id_purchase_execution",
        "warehouse_receipt",
        "purchase_execution",
        ["execution_id"],
        ["execution_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    bind = op.get_bind()
    incompatible = (
        None
        if context.is_offline_mode()
        else bind.execute(
            sa.text("""
        SELECT GROUP_CONCAT(request_id ORDER BY request_id) FROM (
          SELECT request_id FROM purchase_request_item WHERE is_active = 1
          GROUP BY request_id HAVING COUNT(*) > 1
          UNION SELECT request_id FROM purchase_execution GROUP BY request_id HAVING COUNT(*) > 1
          UNION SELECT request_id FROM warehouse_receipt GROUP BY request_id HAVING COUNT(*) > 1
        ) incompatible_requests
    """)
        ).scalar()
    )
    if incompatible:
        raise RuntimeError(
            f"Task06 downgrade would lose multi-item data for request_ids: {incompatible}"
        )
    op.execute(
        sa.text("""
        UPDATE purchase_request r JOIN purchase_request_item i
          ON i.request_id = r.request_id AND i.item_no = 1
        SET r.device_name = i.item_name, r.brand = i.brand_snapshot, r.model = i.model_snapshot,
            r.quantity = i.quantity, r.unit = i.unit
    """)
    )
    op.drop_constraint(
        "fk_warehouse_receipt_execution_id_purchase_execution",
        "warehouse_receipt",
        type_="foreignkey",
    )
    op.drop_index("ix_warehouse_receipt_execution_id", table_name="warehouse_receipt")
    op.create_unique_constraint(
        "uq_warehouse_receipt_request_id", "warehouse_receipt", ["request_id"]
    )
    op.drop_index("ix_warehouse_receipt_request_id", table_name="warehouse_receipt")
    op.drop_constraint(
        op.f("ck_purchase_execution_purchased_quantity_positive"),
        "purchase_execution",
        type_="check",
    )
    op.drop_constraint(
        "fk_purchase_execution_request_item_id_purchase_request_item",
        "purchase_execution",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_purchase_execution_request_item_id", "purchase_execution", type_="unique"
    )
    op.create_unique_constraint(
        "uq_purchase_execution_request_id", "purchase_execution", ["request_id"]
    )
    op.drop_index("ix_purchase_execution_request_id", table_name="purchase_execution")
    op.alter_column(
        "warehouse_receipt", "execution_id", existing_type=sa.BigInteger(), nullable=True
    )
    op.alter_column(
        "purchase_execution", "purchased_quantity", existing_type=sa.Numeric(18, 3), nullable=True
    )
    op.alter_column(
        "purchase_execution", "request_item_id", existing_type=sa.BigInteger(), nullable=True
    )
    op.alter_column("purchase_request", "request_type", existing_type=sa.String(30), nullable=True)
