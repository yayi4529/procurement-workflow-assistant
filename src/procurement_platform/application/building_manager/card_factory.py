# ruff: noqa: RUF001

from procurement_platform.application.card_values import quantity_text
from procurement_platform.application.multi_item_presenter import multi_item_markdown
from procurement_platform.application.status_labels import requirement_status_label
from procurement_platform.domain.enums import RequirementStatus
from procurement_platform.domain.interaction import (
    ActionButton,
    DateInput,
    InteractionElement,
    InteractionView,
    KeyValueField,
    KeyValueSection,
    MarkdownBlock,
    SelectInput,
    SelectOption,
    TextInput,
)
from procurement_platform.domain.requirement import (
    HandlerCandidates,
    RequirementDetail,
    RequirementPage,
    RequirementTransitionResult,
)


class BuildingManagerCardFactory:
    def message(self, title: str, text: str) -> InteractionView:
        return InteractionView(
            title=title,
            elements=(MarkdownBlock(markdown=text),),
            actions=(ActionButton(action_id="building_manager.list_pending", label="返回待办"),),
        )

    def detail(self, detail: RequirementDetail, notice: str | None = None) -> InteractionView:
        applicant = detail.applicant_fields
        review = detail.review_fields
        elements: list[InteractionElement] = []
        if notice:
            elements.append(MarkdownBlock(markdown=notice))
        elements.append(
            KeyValueSection(
                fields=(
                    KeyValueField(label="采购单编号", value=detail.requirement_no),
                    KeyValueField(label="所属楼宇", value=detail.building.building_name),
                    KeyValueField(label="设备名称", value=applicant.device_name or "-"),
                    KeyValueField(
                        label="品牌/型号",
                        value=f"{applicant.brand or '-'} / {applicant.model or '-'}",
                    ),
                    KeyValueField(
                        label="数量",
                        value=f"{quantity_text(applicant.quantity)} {applicant.unit or ''}".strip(),
                    ),
                    KeyValueField(label="需求原因", value=applicant.application_reason or "-"),
                    KeyValueField(label="状态", value=requirement_status_label(detail.status)),
                    KeyValueField(label="申请人", value=detail.applicant_name or "-"),
                    KeyValueField(label="申请人联系方式", value=detail.applicant_mobile or "-"),
                )
            )
        )
        if detail.items:
            elements.append(MarkdownBlock(markdown=multi_item_markdown(detail)))
        if detail.status is RequirementStatus.PENDING_REVIEW:
            for item in detail.items:
                if not item.is_active:
                    continue
                existing = next(
                    (
                        value
                        for value in detail.review_items
                        if value.request_item_id == item.request_item_id
                    ),
                    None,
                )
                elements.extend(
                    (
                        TextInput(
                            name=f"review_supplier_{item.request_item_id}",
                            label=f"{item.item_no}. {item.item_name} 建议供应商ID（选填）",
                            default_value=(
                                str(existing.proposed_supplier_id)
                                if existing and existing.proposed_supplier_id
                                else None
                            ),
                            required=False,
                        ),
                        TextInput(
                            name=f"review_price_{item.request_item_id}",
                            label=f"{item.item_no}. {item.item_name} 预计单价（选填）",
                            default_value=existing.estimated_unit_price if existing else None,
                            required=False,
                        ),
                    )
                )
            specs = (
                (
                    "proposed_supplier_name",
                    "拟定供应商名称",
                    review.proposed_supplier_name if review else None,
                    True,
                ),
                (
                    "supplier_contact_name",
                    "供应商联系人姓名",
                    review.supplier_contact_name if review else None,
                    True,
                ),
                (
                    "supplier_contact_info",
                    "供应商联系方式",
                    review.supplier_contact_info if review else None,
                    True,
                ),
                ("supplier_link", "供应商链接", review.supplier_link if review else None, False),
                (
                    "estimated_unit_price",
                    "预计单价",
                    review.estimated_unit_price if review else None,
                    True,
                ),
                (
                    "contract_type",
                    "合同类型(需要合同时必填)",
                    review.contract_type if review else None,
                    False,
                ),
                ("payment_method", "付款方式", review.payment_method if review else None, True),
                ("warranty_info", "质保信息", review.warranty_info if review else None, True),
                ("review_remark", "楼长备注", review.review_remark if review else None, False),
            )
            elements.extend(
                TextInput(
                    name=name,
                    label=label,
                    default_value=value,
                    required=required and not detail.items,
                )
                for name, label, value, required in specs
            )
            elements.extend(
                (
                    SelectInput(
                        name="need_contract",
                        label="是否需要合同",
                        options=(
                            SelectOption(label="是否需要合同: 是", value="true"),
                            SelectOption(label="是否需要合同: 否", value="false"),
                        ),
                        required=not detail.items,
                        default_value=(
                            None
                            if review is None or review.need_contract is None
                            else str(review.need_contract).lower()
                        ),
                    ),
                    DateInput(
                        name="expected_arrival_date",
                        label="预计到货日期",
                        required=not detail.items,
                        default_value=review.expected_arrival_date if review else None,
                    ),
                )
            )
            if review and review.estimated_total_price is not None:
                elements.append(
                    MarkdownBlock(
                        markdown=f"**预计总价(后端计算):** {review.estimated_total_price}"
                    )
                )
        actions = (
            ActionButton(
                action_id="building_manager.save_review_items",
                label="保存逐项审核",
                value={"requirement_id": detail.requirement_id, "expected_version": detail.version},
                style="primary",
            ),
            ActionButton(
                action_id="building_manager.save_review_fields",
                label="保存审核信息",
                value={"requirement_id": detail.requirement_id, "expected_version": detail.version},
                style="primary",
            ),
            ActionButton(
                action_id="building_manager.prepare_reject",
                label="驳回",
                value={"requirement_id": detail.requirement_id},
                style="danger",
            ),
            ActionButton(
                action_id="building_manager.prepare_submit_purchaser",
                label="提交采购员",
                value={"requirement_id": detail.requirement_id},
            ),
        )
        return InteractionView(
            title="楼长审核采购申请",
            subtitle=(
                "表单底部依次为“是否需要合同”和“预计到货日期”。"
                if detail.status is RequirementStatus.PENDING_REVIEW
                else None
            ),
            elements=tuple(elements),
            actions=actions if detail.status is RequirementStatus.PENDING_REVIEW else actions[-1:],
        )

    def reject_form(self, detail: RequirementDetail) -> InteractionView:
        return InteractionView(
            title="驳回采购申请",
            elements=(TextInput(name="reason", label="驳回原因", required=True),),
            actions=(
                ActionButton(
                    action_id="building_manager.prepare_reject",
                    label="生成确认",
                    value={"requirement_id": detail.requirement_id},
                    style="danger",
                ),
            ),
        )

    def reject_confirmation(
        self, detail: RequirementDetail, reason: str, token: str
    ) -> InteractionView:
        return InteractionView(
            title="确认驳回",
            elements=(MarkdownBlock(markdown=f"驳回原因: {reason}"),),
            actions=(
                ActionButton(
                    action_id="building_manager.confirm_reject",
                    label="确认驳回",
                    value={
                        "requirement_id": detail.requirement_id,
                        "expected_version": detail.version,
                        "reason": reason,
                        "action_token": token,
                    },
                    style="danger",
                ),
            ),
        )

    def purchaser_selection(
        self, detail: RequirementDetail, candidates: HandlerCandidates
    ) -> InteractionView:
        return InteractionView(
            title="选择采购员",
            elements=(
                SelectInput(
                    name="assigned_to_employee_id",
                    label="采购员",
                    options=tuple(
                        SelectOption(label=item.name, value=str(item.employee_id))
                        for item in candidates.items
                    ),
                    required=True,
                    default_value=(
                        str(candidates.auto_selected_employee_id)
                        if candidates.auto_selected_employee_id is not None
                        else str(candidates.items[0].employee_id)
                        if len(candidates.items) == 1
                        else None
                    ),
                ),
            ),
            actions=(
                ActionButton(
                    action_id="building_manager.prepare_submit_purchaser",
                    label="生成确认",
                    value={"requirement_id": detail.requirement_id},
                    style="primary",
                ),
            ),
        )

    def submit_confirmation(
        self, detail: RequirementDetail, employee_id: int, employee_name: str, token: str
    ) -> InteractionView:
        return InteractionView(
            title="确认提交采购员",
            elements=(MarkdownBlock(markdown=f"采购员: {employee_name}"),),
            actions=(
                ActionButton(
                    action_id="building_manager.confirm_submit_purchaser",
                    label="确认提交",
                    value={
                        "requirement_id": detail.requirement_id,
                        "expected_version": detail.version,
                        "assigned_to_employee_id": employee_id,
                        "action_token": token,
                    },
                    style="primary",
                ),
            ),
        )

    def result(self, result: RequirementTransitionResult, title: str) -> InteractionView:
        return InteractionView(
            title=title,
            elements=(
                KeyValueSection(
                    fields=(
                        KeyValueField(label="采购单编号", value=result.requirement_no),
                        KeyValueField(label="状态", value=requirement_status_label(result.status)),
                        KeyValueField(
                            label="当前处理人",
                            value=result.current_handler.name if result.current_handler else "-",
                        ),
                    )
                ),
            ),
            actions=(ActionButton(action_id="building_manager.list_pending", label="返回待办"),),
        )

    def submitted_purchaser(
        self, detail: RequirementDetail, manager_name: str, manager_mobile: str | None
    ) -> InteractionView:
        applicant = detail.applicant_fields
        review = detail.review_fields
        return InteractionView(
            title="已提交采购员",
            elements=(
                KeyValueSection(
                    fields=(
                        KeyValueField(label="采购单编号", value=detail.requirement_no),
                        KeyValueField(label="状态", value=requirement_status_label(detail.status)),
                        KeyValueField(
                            label="当前处理人",
                            value=detail.current_handler.name if detail.current_handler else "-",
                        ),
                        KeyValueField(label="楼长姓名", value=manager_name),
                        KeyValueField(label="楼长联系方式", value=manager_mobile or "-"),
                        KeyValueField(label="设备名称", value=applicant.device_name or "-"),
                        KeyValueField(
                            label="品牌/型号",
                            value=f"{applicant.brand or '-'} / {applicant.model or '-'}",
                        ),
                        KeyValueField(
                            label="数量",
                            value=(
                                f"{quantity_text(applicant.quantity)} {applicant.unit or ''}"
                            ).strip(),
                        ),
                        KeyValueField(
                            label="供应商名称",
                            value=(review.proposed_supplier_name if review else None) or "-",
                        ),
                        KeyValueField(
                            label="供应商联系人",
                            value=(review.supplier_contact_name if review else None) or "-",
                        ),
                        KeyValueField(
                            label="供应商联系方式",
                            value=(review.supplier_contact_info if review else None) or "-",
                        ),
                        KeyValueField(
                            label="预计单价",
                            value=f"{review.estimated_unit_price} 元"
                            if review and review.estimated_unit_price
                            else "-",
                        ),
                        KeyValueField(
                            label="付款方式",
                            value=(review.payment_method if review else None) or "-",
                        ),
                        KeyValueField(
                            label="质保信息",
                            value=(review.warranty_info if review else None) or "-",
                        ),
                    )
                ),
            ),
            actions=(ActionButton(action_id="building_manager.list_pending", label="返回待办"),),
        )

    def listing(self, page: RequirementPage) -> InteractionView:
        return InteractionView(
            title="楼长待审核",
            elements=(
                MarkdownBlock(
                    markdown="\n".join(
                        f"- {item.requirement_no} | {item.device_name or '-'}"
                        for item in page.items
                    )
                    or "暂无待审核申请"
                ),
            ),
            actions=tuple(
                ActionButton(
                    action_id="building_manager.open_requirement",
                    label=item.requirement_no,
                    value={"requirement_id": item.requirement_id},
                )
                for item in page.items
            ),
        )
