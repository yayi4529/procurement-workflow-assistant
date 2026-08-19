from decimal import Decimal

import pytest
from sqlalchemy import inspect

from app.core.exceptions import AppError
from app.db.base import Base
from app.domain.enums import (
    ItemFulfillmentStatus,
    PurchaseItemKind,
    RequestType,
)
from app.models.procurement import PurchaseExecution, PurchaseRequestItem
from app.schemas.procurement import SavePurchaseItemRequest, SubmitWarehouseRequest
from app.services.fulfillment import ProcurementFulfillmentService


def _item(*, active: bool = True, warehouse: bool = True) -> PurchaseRequestItem:
    return PurchaseRequestItem(
        request_item_id=11,
        request_id=1,
        item_no=1,
        item_kind=PurchaseItemKind.COMPONENT.value,
        item_name="蓄电池",
        quantity=Decimal("3.000"),
        unit="块",
        requires_warehouse=warehouse,
        is_active=active,
    )


def _execution() -> PurchaseExecution:
    return PurchaseExecution(
        execution_id=21,
        request_id=1,
        request_item_id=11,
        purchased_quantity=Decimal("3.000"),
    )


def test_task06_enums_are_stable_strings() -> None:
    assert [value.value for value in RequestType] == [
        "PURCHASE",
        "MAINTENANCE",
        "FAULT",
        "RETIREMENT",
    ]
    assert PurchaseItemKind.SERVICE.value == "SERVICE"


def test_task06_adds_exactly_two_procurement_detail_tables() -> None:
    assert "purchase_request_item" in Base.metadata.tables
    assert "purchase_review_item" in Base.metadata.tables
    assert "purchase_execution_item" not in Base.metadata.tables
    assert "warehouse_receipt_item" not in Base.metadata.tables
    execution = inspect(Base.metadata.tables["purchase_execution"])
    receipt = inspect(Base.metadata.tables["warehouse_receipt"])
    assert "request_item_id" in execution.columns
    assert "purchased_quantity" in execution.columns
    assert "execution_id" in receipt.columns


@pytest.mark.parametrize(
    ("active", "warehouse", "execution", "received", "expected"),
    [
        (False, True, False, "0", ItemFulfillmentStatus.INACTIVE),
        (True, True, False, "0", ItemFulfillmentStatus.PENDING_PURCHASE),
        (True, False, True, "0", ItemFulfillmentStatus.FULFILLED),
        (True, True, True, "0", ItemFulfillmentStatus.PURCHASED),
        (True, True, True, "1", ItemFulfillmentStatus.PARTIALLY_RECEIVED),
        (True, True, True, "3", ItemFulfillmentStatus.FULFILLED),
    ],
)
def test_item_fulfillment_is_derived(
    active: bool,
    warehouse: bool,
    execution: bool,
    received: str,
    expected: ItemFulfillmentStatus,
) -> None:
    result = ProcurementFulfillmentService.get_item_fulfillment(
        _item(active=active, warehouse=warehouse),
        _execution() if execution else None,
        Decimal(received),
    )
    assert result.status == expected


def test_over_receipt_is_an_invariant_violation() -> None:
    with pytest.raises(AppError) as exc_info:
        ProcurementFulfillmentService.get_item_fulfillment(_item(), _execution(), Decimal("3.001"))
    assert exc_info.value.code == "FULFILLMENT_INVARIANT_VIOLATION"


def test_receipt_validation_rejects_service_and_over_receipt() -> None:
    service = ProcurementFulfillmentService()
    with pytest.raises(AppError) as service_error:
        service.validate_receipt_quantity(
            _item(warehouse=False), _execution(), Decimal("0"), Decimal("1")
        )
    assert service_error.value.code == "WAREHOUSE_NOT_REQUIRED"
    with pytest.raises(AppError) as over_error:
        service.validate_receipt_quantity(_item(), _execution(), Decimal("2.500"), Decimal("1.000"))
    assert over_error.value.code == "OVER_RECEIPT"


def test_item_purchase_requires_action_token_and_service_completion_has_no_handler() -> None:
    payload = SavePurchaseItemRequest.model_validate(
        {
            "expected_version": 3,
            "action_token": "task06b-purchase-item-1",
            "fields": {
                "supplier_id": 1,
                "actual_unit_price": "10.00",
                "purchased_at": "2026-08-18T10:00:00",
            },
        }
    )
    assert payload.action_token == "task06b-purchase-item-1"
    completion = SubmitWarehouseRequest(
        expected_version=4,
        action_token="task06b-service-complete",
        assigned_to_employee_id=None,
    )
    assert completion.assigned_to_employee_id is None
