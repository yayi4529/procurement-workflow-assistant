from dataclasses import dataclass
from decimal import Decimal

from app.core.exceptions import AppError
from app.domain.enums import ItemFulfillmentStatus
from app.models.procurement import PurchaseExecution, PurchaseRequestItem


@dataclass(frozen=True)
class ItemFulfillment:
    request_item_id: int
    status: ItemFulfillmentStatus
    purchased_quantity: Decimal
    received_quantity: Decimal


class ProcurementFulfillmentService:
    @staticmethod
    def get_item_fulfillment(
        item: PurchaseRequestItem,
        execution: PurchaseExecution | None,
        received_total: Decimal = Decimal("0"),
    ) -> ItemFulfillment:
        if not item.is_active:
            status = ItemFulfillmentStatus.INACTIVE
        elif execution is None:
            status = ItemFulfillmentStatus.PENDING_PURCHASE
        elif not item.requires_warehouse:
            if received_total:
                raise AppError(
                    "FULFILLMENT_INVARIANT_VIOLATION", "无需入库的采购项存在收货记录", 500
                )
            status = ItemFulfillmentStatus.FULFILLED
        elif received_total > execution.purchased_quantity:
            raise AppError("FULFILLMENT_INVARIANT_VIOLATION", "累计收货数量超过采购数量", 500)
        elif received_total == execution.purchased_quantity:
            status = ItemFulfillmentStatus.FULFILLED
        elif received_total > 0:
            status = ItemFulfillmentStatus.PARTIALLY_RECEIVED
        else:
            status = ItemFulfillmentStatus.PURCHASED
        return ItemFulfillment(
            request_item_id=item.request_item_id,
            status=status,
            purchased_quantity=(execution.purchased_quantity if execution else Decimal("0")),
            received_quantity=received_total,
        )

    @staticmethod
    def validate_execution_for_item(
        item: PurchaseRequestItem, execution: PurchaseExecution | None
    ) -> None:
        if not item.is_active:
            raise AppError("INVALID_REQUEST_ITEM", "采购项已停用", 409)
        if execution is not None and execution.request_id != item.request_id:
            raise AppError("FULFILLMENT_INVARIANT_VIOLATION", "采购执行与采购项不属于同一申请", 500)

    @staticmethod
    def validate_receipt_quantity(
        item: PurchaseRequestItem,
        execution: PurchaseExecution,
        received_total: Decimal,
        new_quantity: Decimal,
    ) -> None:
        if not item.requires_warehouse:
            raise AppError("WAREHOUSE_NOT_REQUIRED", "该采购项无需入库", 409)
        if execution.request_id != item.request_id:
            raise AppError("FULFILLMENT_INVARIANT_VIOLATION", "收货执行与采购项不一致", 500)
        if new_quantity <= 0:
            raise AppError("VALIDATION_ERROR", "收货数量必须大于零", 422)
        if received_total + new_quantity > execution.purchased_quantity:
            raise AppError("OVER_RECEIPT", "累计收货数量不能超过采购数量", 409)

    @staticmethod
    def all_active_items_executed(
        items: list[PurchaseRequestItem], executions: list[PurchaseExecution]
    ) -> bool:
        executed_ids = {execution.request_item_id for execution in executions}
        return all(item.request_item_id in executed_ids for item in items if item.is_active)

    @staticmethod
    def all_warehouse_items_fulfilled(
        items: list[PurchaseRequestItem], fulfillment: dict[int, ItemFulfillment]
    ) -> bool:
        return all(
            fulfillment[item.request_item_id].status == ItemFulfillmentStatus.FULFILLED
            for item in items
            if item.is_active and item.requires_warehouse
        )
