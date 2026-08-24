"""add governed procurement analytics views

Revision ID: c7a21a10b001
Revises: b6f11c06a002
Create Date: 2026-08-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c7a21a10b001"
down_revision: str | Sequence[str] | None = "b6f11c06a002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REQUEST_VIEW = """
SELECT pr.request_no, pr.status AS request_status, pr.request_type,
       pr.building_id, b.building_name, pr.device_profession, pr.device_name,
       pr.created_at, pr.submitted_at, pr.completed_at
FROM purchase_request pr
JOIN building b ON b.building_id = pr.building_id
"""

ITEM_VIEW = """
SELECT pr.request_no, pr.status AS request_status, pr.request_type,
       pr.building_id, b.building_name, pr.device_profession, pr.device_name,
       pr.created_at, pr.submitted_at, pr.completed_at,
       pri.request_item_id, pri.item_name, pri.item_kind,
       COALESCE(pri.brand_snapshot, pr.brand) AS brand,
       COALESCE(pri.model_snapshot, pr.model) AS model,
       pri.quantity AS requested_quantity, pe.purchased_quantity,
       pri.unit, pe.supplier_id, pe.supplier_name_snapshot AS supplier_name,
       pe.actual_unit_price, pe.actual_total_price, pe.purchased_at,
       receipts.received_quantity, receipts.last_received_at,
       CASE WHEN pe.purchased_at IS NOT NULL AND receipts.last_received_at IS NOT NULL
            THEN TIMESTAMPDIFF(DAY, pe.purchased_at, receipts.last_received_at) END AS delivery_days
FROM purchase_request pr
JOIN building b ON b.building_id = pr.building_id
JOIN purchase_request_item pri ON pri.request_id = pr.request_id AND pri.is_active = 1
LEFT JOIN purchase_execution pe ON pe.request_item_id = pri.request_item_id
LEFT JOIN (
    SELECT execution_id, SUM(received_quantity) AS received_quantity,
           MAX(received_at) AS last_received_at
    FROM warehouse_receipt GROUP BY execution_id
) receipts ON receipts.execution_id = pe.execution_id
"""


def upgrade() -> None:
    op.execute(f"CREATE OR REPLACE VIEW analytics_purchase_request_fact AS {REQUEST_VIEW}")
    op.execute(f"CREATE OR REPLACE VIEW analytics_purchase_item_fact AS {ITEM_VIEW}")
    op.execute(
        "CREATE OR REPLACE VIEW analytics_purchase_request_fact_real AS "
        f"{REQUEST_VIEW} WHERE pr.request_no NOT LIKE 'TEST-%'"
    )
    op.execute(
        "CREATE OR REPLACE VIEW analytics_purchase_item_fact_real AS "
        f"{ITEM_VIEW} WHERE pr.request_no NOT LIKE 'TEST-%'"
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS analytics_purchase_item_fact_real")
    op.execute("DROP VIEW IF EXISTS analytics_purchase_request_fact_real")
    op.execute("DROP VIEW IF EXISTS analytics_purchase_item_fact")
    op.execute("DROP VIEW IF EXISTS analytics_purchase_request_fact")
