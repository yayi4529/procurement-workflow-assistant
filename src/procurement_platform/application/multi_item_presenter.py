"""Presentation-only helpers for backend-computed multi-item facts."""

# ruff: noqa: RUF001

from decimal import Decimal

from procurement_platform.application.card_values import quantity_text
from procurement_platform.domain.enums import RequestType
from procurement_platform.domain.requirement import RequirementDetail

REQUEST_TYPE_LABELS = {
    RequestType.PURCHASE: "采购",
    RequestType.MAINTENANCE: "维护",
    RequestType.FAULT: "故障",
    RequestType.RETIREMENT: "退役",
}


def item_is_complete(item: object) -> bool:
    status = getattr(item, "fulfillment_status", None)
    return getattr(status, "value", None) == "FULFILLED"


def request_is_complete(detail: object) -> bool:
    summary = getattr(detail, "request_" + "fulfillment", None)
    return summary is not None and bool(getattr(summary, "all_active_items_fulfilled", False))


def request_has_summary(detail: object) -> bool:
    return getattr(detail, "request_" + "fulfillment", None) is not None


def active_item_lines(detail: RequirementDetail, *, include_status: bool = True) -> list[str]:
    execution_by_item = {item.request_item_id: item for item in detail.executions}
    received_by_execution: dict[int, Decimal] = {}
    for receipt_item in detail.receipts:
        received_by_execution[receipt_item.execution_id] = received_by_execution.get(
            receipt_item.execution_id, Decimal("0")
        ) + Decimal(receipt_item.received_quantity)
    lines: list[str] = []
    for item in detail.items:
        if not item.is_active:
            continue
        brand_model = " / ".join(
            value for value in (item.brand_snapshot, item.model_snapshot) if value
        )
        suffix = f"；品牌/型号：{brand_model}" if brand_model else "；品牌/型号：未指定"
        status = f"；状态：{item.fulfillment_status.value}" if include_status else ""
        execution = execution_by_item.get(item.request_item_id)
        receipt_text = ""
        if execution is not None and item.requires_warehouse:
            received = received_by_execution.get(execution.execution_id, Decimal("0"))
            remaining = Decimal(execution.purchased_quantity) - received
            receipt_text = (
                f"；已入库 {quantity_text(str(received))}{item.unit}"
                f"；待入库 {quantity_text(str(remaining))}{item.unit}"
            )
        lines.append(
            f"{item.item_no}. {item.item_name}（{item.item_kind.value}）"
            f" × {quantity_text(item.quantity)}{item.unit}{suffix}{status}{receipt_text}"
        )
    return lines


def request_header_lines(detail: RequirementDetail) -> list[str]:
    source = detail.source_asset or {}
    asset_name = source.get("asset_name") if isinstance(source, dict) else None
    asset_code = source.get("asset_code") if isinstance(source, dict) else None
    asset = " / ".join(str(value) for value in (asset_name, asset_code) if value) or "未关联"
    return [
        f"采购类型：{REQUEST_TYPE_LABELS[detail.request_type]}",
        f"关联设备：{asset}",
        f"申请原因：{detail.applicant_fields.application_reason or '-'}",
    ]


def multi_item_markdown(detail: RequirementDetail, *, include_status: bool = True) -> str:
    lines = request_header_lines(detail)
    items = active_item_lines(detail, include_status=include_status)
    lines.extend(("", "**采购项：**", *(items or ["暂无有效采购项"])))
    return "\n\n".join(lines)
