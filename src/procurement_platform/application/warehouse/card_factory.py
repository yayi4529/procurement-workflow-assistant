from decimal import Decimal
from uuid import uuid4

from procurement_platform.application.card_values import quantity_text
from procurement_platform.application.multi_item_presenter import (
    item_is_complete,
    multi_item_markdown,
)
from procurement_platform.application.status_labels import requirement_status_label
from procurement_platform.domain.interaction import (
    ActionButton,
    InteractionElement,
    InteractionView,
    KeyValueField,
    KeyValueSection,
    MarkdownBlock,
    TextInput,
)
from procurement_platform.domain.requirement import (
    RequirementCompletionResult,
    RequirementDetail,
    RequirementPage,
)


class WarehouseCardFactory:
    def detail(self, detail: RequirementDetail, notice: str | None = None) -> InteractionView:
        warehouse = detail.warehouse_fields
        elements: list[InteractionElement] = []
        if notice:
            elements.append(MarkdownBlock(markdown=notice))
        elements.append(
            KeyValueSection(
                fields=(
                    KeyValueField(label="采购编号", value=detail.requirement_no),
                    KeyValueField(label="设备", value=detail.applicant_fields.device_name or "-"),
                    KeyValueField(
                        label="品牌/型号",
                        value=f"{detail.applicant_fields.brand or '-'} / "
                        f"{detail.applicant_fields.model or '-'}",
                    ),
                    KeyValueField(
                        label="采购数量",
                        value=f"{quantity_text(detail.applicant_fields.quantity)} "
                        f"{detail.applicant_fields.unit or ''}".strip(),
                    ),
                    KeyValueField(label="供应商", value=self._supplier(detail)),
                    KeyValueField(
                        label="实际总价",
                        value=(
                            detail.purchase_fields.actual_total_price
                            if detail.purchase_fields
                            and detail.purchase_fields.actual_total_price is not None
                            else "-"
                        ),
                    ),
                    KeyValueField(label="状态", value=requirement_status_label(detail.status)),
                )
            )
        )
        if detail.items:
            elements.append(MarkdownBlock(markdown=multi_item_markdown(detail)))
            execution_by_item = {value.request_item_id: value for value in detail.executions}
            for item in detail.items:
                execution = execution_by_item.get(item.request_item_id)
                if not item.is_active or not item.requires_warehouse or execution is None:
                    continue
                elements.append(
                    TextInput(
                        name=f"receipt_quantity_{execution.execution_id}",
                        label=f"{item.item_no}. {item.item_name} 本次入库数量",
                        required=False,
                    )
                )
        elements.extend(
            (
                TextInput(
                    name="warehouse_location",
                    label="仓库位置",
                    default_value=warehouse.warehouse_location if warehouse else None,
                    required=True,
                ),
                TextInput(
                    name="received_quantity",
                    label="实际入库数量",
                    default_value=(
                        quantity_text(warehouse.received_quantity, empty="") if warehouse else None
                    ),
                    required=True,
                ),
                TextInput(
                    name="receipt_remark",
                    label="入库备注(少收时必填)",
                    default_value=warehouse.receipt_remark if warehouse else None,
                    required=False,
                ),
            )
        )
        return InteractionView(
            title="仓库入库处理",
            elements=tuple(elements),
            actions=(
                *(
                    ActionButton(
                        action_id="warehouse.append_receipt",
                        label=f"入库 {item.item_no}. {item.item_name}",
                        value={
                            "requirement_id": detail.requirement_id,
                            "execution_id": execution.execution_id,
                            "expected_version": detail.version,
                            "action_token": str(uuid4()),
                        },
                        style="primary",
                    )
                    for item in detail.items
                    for execution in detail.executions
                    if item.is_active
                    and item.requires_warehouse
                    and execution.request_item_id == item.request_item_id
                    and not item_is_complete(item)
                ),
                ActionButton(
                    action_id="warehouse.save_fields",
                    label="保存入库信息",
                    value={
                        "requirement_id": detail.requirement_id,
                        "expected_version": detail.version,
                    },
                    style="primary",
                ),
                ActionButton(
                    action_id="warehouse.prepare_complete",
                    label="确认完成入库",
                    value={"requirement_id": detail.requirement_id},
                ),
            ),
        )

    def listing(self, page: RequirementPage) -> InteractionView:
        return InteractionView(
            title="仓库待办",
            elements=(
                MarkdownBlock(
                    markdown="\n".join(
                        f"- {item.requirement_no} | {item.device_name or '-'} | "
                        f"{requirement_status_label(item.status)}"
                        for item in page.items
                    )
                    or "暂无待入库任务"
                ),
            ),
            actions=tuple(
                ActionButton(
                    action_id="warehouse.open_requirement",
                    label=item.requirement_no,
                    value={"requirement_id": item.requirement_id},
                )
                for item in page.items
            ),
        )

    def confirmation(self, detail: RequirementDetail, action_token: str) -> InteractionView:
        warehouse = detail.warehouse_fields
        assert warehouse is not None
        requested = detail.applicant_fields.quantity
        notice = (
            "\n\n**少收提示: 实际数量少于申请数量, 备注将由后端最终校验。**"
            if requested
            and warehouse.received_quantity
            and Decimal(warehouse.received_quantity) < Decimal(requested)
            else ""
        )
        return InteractionView(
            title="确认一次性完成入库",
            elements=(
                MarkdownBlock(
                    markdown=f"仓库位置: {warehouse.warehouse_location}\n\n"
                    f"实际入库数量: {quantity_text(warehouse.received_quantity)}\n\n"
                    f"备注: {warehouse.receipt_remark or '-'}{notice}"
                ),
            ),
            actions=(
                ActionButton(
                    action_id="warehouse.confirm_complete",
                    label="确认完成",
                    value={
                        "requirement_id": detail.requirement_id,
                        "expected_version": detail.version,
                        "action_token": action_token,
                    },
                    style="primary",
                ),
            ),
        )

    def result(self, result: RequirementCompletionResult) -> InteractionView:
        return InteractionView(
            title="入库已完成",
            elements=(
                KeyValueSection(
                    fields=(
                        KeyValueField(label="采购单编号", value=result.requirement_no),
                        KeyValueField(label="状态", value=requirement_status_label(result.status)),
                        KeyValueField(label="完成时间", value=result.completed_at.isoformat()),
                        KeyValueField(
                            label="当前处理人",
                            value=result.current_handler.name if result.current_handler else "-",
                        ),
                    )
                ),
            ),
        )

    @staticmethod
    def _supplier(detail: RequirementDetail) -> str:
        if detail.purchase_fields and detail.purchase_fields.supplier_name:
            return detail.purchase_fields.supplier_name
        if detail.review_fields and detail.review_fields.proposed_supplier_name:
            return detail.review_fields.proposed_supplier_name
        return "-"
