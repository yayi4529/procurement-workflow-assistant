from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import (
    PurchaseExecution,
    PurchaseRequestItem,
    Supplier,
    SupplierBlacklist,
    WarehouseReceipt,
)
from app.repositories.suppliers import effective_blacklist_condition
from app.services.recommendation.types import HistoryEvidence, ItemRef


class RecommendationCoreRepository:
    async def get_item(self, session: AsyncSession, request_item_id: int) -> ItemRef | None:
        item = await session.get(PurchaseRequestItem, request_item_id)
        if item is None or not item.is_active:
            return None
        return ItemRef(
            request_id=item.request_id,
            request_item_id=item.request_item_id,
            equipment_category_id=item.equipment_category_id,
            equipment_model_id=item.equipment_model_id,
            item_name=item.item_name,
            brand=item.brand_snapshot,
            model=item.model_snapshot,
            requires_warehouse=item.requires_warehouse,
        )

    async def history_for_category(
        self,
        session: AsyncSession,
        *,
        category_id: int,
        exclude_request_item_id: int,
        now: datetime,
    ) -> list[HistoryEvidence]:
        final_receipt = (
            select(
                WarehouseReceipt.execution_id,
                func.max(WarehouseReceipt.received_at).label("final_received_at"),
            )
            .group_by(WarehouseReceipt.execution_id)
            .subquery()
        )
        rows = (
            await session.execute(
                select(
                    PurchaseRequestItem,
                    PurchaseExecution,
                    Supplier,
                    final_receipt.c.final_received_at,
                )
                .join(
                    PurchaseExecution,
                    PurchaseExecution.request_item_id == PurchaseRequestItem.request_item_id,
                )
                .join(Supplier, Supplier.supplier_id == PurchaseExecution.supplier_id)
                .outerjoin(
                    final_receipt,
                    final_receipt.c.execution_id == PurchaseExecution.execution_id,
                )
                .where(
                    PurchaseRequestItem.equipment_category_id == category_id,
                    PurchaseRequestItem.request_item_id != exclude_request_item_id,
                    PurchaseRequestItem.is_active.is_(True),
                )
                .order_by(PurchaseExecution.purchased_at.desc(), PurchaseExecution.execution_id)
            )
        ).all()
        supplier_ids = {supplier.supplier_id for _, _, supplier, _ in rows}
        blacklisted_ids: set[int] = set()
        if supplier_ids:
            blacklisted_ids = set(
                (
                    await session.scalars(
                        select(SupplierBlacklist.supplier_id)
                        .where(
                            SupplierBlacklist.supplier_id.in_(supplier_ids),
                            effective_blacklist_condition(now),
                        )
                        .distinct()
                    )
                ).all()
            )
        return [
            HistoryEvidence(
                request_id=item.request_id,
                request_item_id=item.request_item_id,
                equipment_category_id=item.equipment_category_id,
                equipment_model_id=item.equipment_model_id,
                item_name=item.item_name,
                brand=item.brand_snapshot,
                model=item.model_snapshot,
                requires_warehouse=item.requires_warehouse,
                execution_id=execution.execution_id,
                supplier_id=supplier.supplier_id,
                supplier_name=execution.supplier_name_snapshot,
                supplier_active=supplier.status,
                actual_unit_price=execution.actual_unit_price,
                purchased_at=execution.purchased_at,
                final_received_at=final_received_at,
                active_blacklist=supplier.supplier_id in blacklisted_ids,
            )
            for item, execution, supplier, final_received_at in rows
        ]
