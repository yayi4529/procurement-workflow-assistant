from procurement_platform.application.assistant.tooling.multi_item import (
    DraftItemChange,
    UpdateMultiItemDraftArgs,
    UpdateMultiItemDraftTool,
)
from procurement_platform.application.assistant.unit_defaults import default_procurement_unit
from procurement_platform.domain.enums import PurchaseItemKind


def test_default_unit_uses_item_kind_without_applicant_input() -> None:
    assert default_procurement_unit("环境检测仪", PurchaseItemKind.EQUIPMENT) == "台"
    assert default_procurement_unit("巡检服务", PurchaseItemKind.SERVICE) == "次"
    assert default_procurement_unit("开关电源", PurchaseItemKind.COMPONENT) == "个"


def test_new_multi_item_gets_unit_without_applicant_input() -> None:
    args = UpdateMultiItemDraftArgs(
        operation="ADD",
        items=(
            DraftItemChange(
                item_kind=PurchaseItemKind.EQUIPMENT,
                item_name="环境检测仪",
                quantity="2",
            ),
        ),
    )

    items = UpdateMultiItemDraftTool._apply_items((), args)

    assert items[0].quantity == "2"
    assert items[0].unit == "台"


def test_explicit_applicant_unit_is_preserved() -> None:
    args = UpdateMultiItemDraftArgs(
        operation="ADD",
        items=(
            DraftItemChange(
                item_kind=PurchaseItemKind.COMPONENT,
                item_name="电池组",
                quantity="1",
                unit="组",
            ),
        ),
    )

    items = UpdateMultiItemDraftTool._apply_items((), args)

    assert items[0].unit == "组"
