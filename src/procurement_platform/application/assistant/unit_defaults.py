"""Deterministic procurement-unit defaults for applicant drafts."""

from procurement_platform.domain.enums import PurchaseItemKind

_EQUIPMENT_HINTS = (
    "服务器",
    "交换机",
    "路由器",
    "打印机",
    "电脑",
    "空调",
    "检测仪",
    "传感器",
    "UPS",
    "设备",
    "主机",
)


def default_procurement_unit(
    item_name: str | None,
    item_kind: PurchaseItemKind | None = None,
) -> str:
    """Choose a stable unit without asking the applicant."""
    if item_kind is PurchaseItemKind.SERVICE:
        return "次"
    if item_kind is PurchaseItemKind.EQUIPMENT:
        return "台"
    normalized = (item_name or "").strip()
    if any(hint.casefold() in normalized.casefold() for hint in _EQUIPMENT_HINTS):
        return "台"
    return "个"
