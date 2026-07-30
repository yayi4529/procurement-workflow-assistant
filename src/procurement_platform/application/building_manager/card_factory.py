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
                        label="数量", value=f"{applicant.quantity or '-'} {applicant.unit or ''}"
                    ),
                    KeyValueField(label="需求原因", value=applicant.application_reason or "-"),
                    KeyValueField(label="状态", value=detail.status.value),
                    KeyValueField(label="版本", value=str(detail.version)),
                )
            )
        )
        if detail.status is RequirementStatus.PENDING_REVIEW:
            specs = (
                (
                    "proposed_supplier_id",
                    "拟定供应商 ID",
                    str(review.proposed_supplier_id)
                    if review and review.proposed_supplier_id
                    else None,
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
                ("warranty_info", "质保信息", review.warranty_info if review else None, False),
                ("review_remark", "楼长备注", review.review_remark if review else None, False),
            )
            elements.extend(
                TextInput(name=name, label=label, default_value=value, required=required)
                for name, label, value, required in specs
            )
            elements.extend(
                (
                    SelectInput(
                        name="need_contract",
                        label="是否需要合同",
                        options=(
                            SelectOption(label="是", value="true"),
                            SelectOption(label="否", value="false"),
                        ),
                        required=True,
                        default_value=(
                            None
                            if review is None or review.need_contract is None
                            else str(review.need_contract).lower()
                        ),
                    ),
                    DateInput(
                        name="expected_arrival_date",
                        label="预计到货日期",
                        required=True,
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
            elements.append(
                MarkdownBlock(markdown=f"**当前缺少:** {'、'.join(detail.missing_fields) or '无'}")
            )
        actions = (
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
            ActionButton(
                action_id="building_manager.refresh",
                label="刷新",
                value={"requirement_id": detail.requirement_id},
            ),
        )
        return InteractionView(
            title="楼长审核采购申请",
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
                        KeyValueField(label="状态", value=result.status.value),
                        KeyValueField(
                            label="当前处理人",
                            value=result.current_handler.name if result.current_handler else "-",
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
