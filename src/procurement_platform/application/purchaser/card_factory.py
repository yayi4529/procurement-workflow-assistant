from uuid import uuid4

from procurement_platform.domain.enums import RequirementStatus
from procurement_platform.domain.interaction import (
    ActionButton,
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
    SupplierDetail,
    SupplierPage,
)


class PurchaserCardFactory:
    def message(self, title: str, text: str) -> InteractionView:
        return InteractionView(title=title, elements=(MarkdownBlock(markdown=text),))

    def supplier_search_form(self) -> InteractionView:
        return InteractionView(
            title="搜索供应商",
            elements=(TextInput(name="keyword", label="名称或统一社会信用代码", required=True),),
            actions=(
                ActionButton(action_id="purchaser.search_supplier", label="搜索", style="primary"),
            ),
        )

    def new_supplier_form(self) -> InteractionView:
        fields = (
            ("supplier_name", "供应商名称", True),
            ("supplier_tax_number", "统一社会信用代码", False),
            ("bank_name", "开户行", False),
            ("bank_account", "银行账号(敏感)", False),
            ("registered_address", "注册地址", False),
            ("contract_contact_info", "合同联系方式", False),
        )
        return InteractionView(
            title="新建或补充供应商",
            elements=tuple(
                TextInput(name=name, label=label, required=required)
                for name, label, required in fields
            ),
            actions=(
                ActionButton(
                    action_id="purchaser.create_supplier", label="创建供应商", style="primary"
                ),
            ),
        )

    def detail(self, detail: RequirementDetail, notice: str | None = None) -> InteractionView:
        purchase = detail.purchase_fields
        elements: list[InteractionElement] = []
        if notice:
            elements.append(MarkdownBlock(markdown=notice))
        elements.append(
            KeyValueSection(
                fields=(
                    KeyValueField(label="采购单编号", value=detail.requirement_no),
                    KeyValueField(label="设备", value=detail.applicant_fields.device_name or "-"),
                    KeyValueField(
                        label="数量",
                        value=f"{detail.applicant_fields.quantity or '-'} "
                        f"{detail.applicant_fields.unit or ''}",
                    ),
                    KeyValueField(label="状态", value=detail.status.value),
                    KeyValueField(label="版本", value=str(detail.version)),
                )
            )
        )
        if detail.status is RequirementStatus.PURCHASING:
            specs = (
                (
                    "supplier_id",
                    "正式供应商 ID",
                    str(purchase.supplier_id) if purchase and purchase.supplier_id else None,
                ),
                ("supplier_tax_number", "税号", purchase.supplier_tax_number if purchase else None),
                ("bank_name", "开户行", purchase.bank_name if purchase else None),
                ("bank_account", "银行账号(敏感)", None),
                (
                    "registered_address",
                    "注册地址",
                    purchase.registered_address if purchase else None,
                ),
                (
                    "contract_contact_info",
                    "合同联系方式",
                    purchase.contract_contact_info if purchase else None,
                ),
                ("actual_unit_price", "实际单价", purchase.actual_unit_price if purchase else None),
                ("tax_rate", "税率", purchase.tax_rate if purchase else None),
                (
                    "purchased_at",
                    "采购时间(ISO 8601)",
                    purchase.purchased_at.isoformat()
                    if purchase and purchase.purchased_at
                    else None,
                ),
                ("purchase_remark", "采购备注", purchase.purchase_remark if purchase else None),
            )
            elements.extend(
                TextInput(
                    name=name,
                    label=label,
                    default_value=default,
                    required=name not in {"purchase_remark"},
                )
                for name, label, default in specs
            )
            elements.append(
                SelectInput(
                    name="update_supplier_profile",
                    label="同步更新供应商档案(默认否)",
                    options=(
                        SelectOption(label="否", value="false"),
                        SelectOption(label="是, 我明确确认", value="true"),
                    ),
                    required=True,
                    default_value="true"
                    if purchase and purchase.update_supplier_profile
                    else "false",
                )
            )
            if purchase and purchase.actual_total_price:
                elements.append(
                    MarkdownBlock(markdown=f"**实际总价(后端计算):** {purchase.actual_total_price}")
                )
            elements.append(
                MarkdownBlock(markdown=f"**当前缺少:** {'、'.join(detail.missing_fields) or '无'}")
            )
        actions: list[ActionButton] = [
            ActionButton(
                action_id="purchaser.refresh",
                label="刷新",
                value={"requirement_id": detail.requirement_id},
            )
        ]
        if detail.status is RequirementStatus.PENDING_PURCHASE:
            actions.insert(
                0,
                ActionButton(
                    action_id="purchaser.start_purchase",
                    label="开始采购",
                    value={
                        "requirement_id": detail.requirement_id,
                        "expected_version": detail.version,
                        "action_token": str(uuid4()),
                    },
                    style="primary",
                ),
            )
        if detail.status is RequirementStatus.PURCHASING:
            actions[0:0] = [
                ActionButton(action_id="purchaser.search_supplier", label="搜索供应商"),
                ActionButton(
                    action_id="purchaser.save_purchase_fields",
                    label="保存采购信息",
                    value={
                        "requirement_id": detail.requirement_id,
                        "expected_version": detail.version,
                    },
                    style="primary",
                ),
                ActionButton(
                    action_id="purchaser.prepare_submit_warehouse",
                    label="提交仓库",
                    value={"requirement_id": detail.requirement_id},
                ),
            ]
        return InteractionView(
            title="采购员采购执行", elements=tuple(elements), actions=tuple(actions)
        )

    def listing(self, page: RequirementPage) -> InteractionView:
        return InteractionView(
            title="采购员待办",
            elements=(
                MarkdownBlock(
                    markdown="\n".join(
                        f"- {item.requirement_no} | {item.device_name or '-'} | {item.status.value}"
                        for item in page.items
                    )
                    or "暂无待采购任务"
                ),
            ),
            actions=(
                *(
                    ActionButton(
                        action_id="purchaser.open_requirement",
                        label=item.requirement_no,
                        value={"requirement_id": item.requirement_id},
                    )
                    for item in page.items
                ),
                ActionButton(action_id="purchaser.prepare_create_supplier", label="新建供应商"),
            ),
        )

    def supplier_listing(self, page: SupplierPage) -> InteractionView:
        return InteractionView(
            title="供应商候选",
            elements=(
                MarkdownBlock(
                    markdown="\n".join(
                        f"- {item.supplier_name} | 税号 {item.supplier_tax_number or '-'}"
                        f"{' | 有效黑名单' if item.blacklist and item.blacklist.active else ''}"
                        for item in page.items
                    )
                    or "未找到供应商"
                ),
            ),
            actions=tuple(
                ActionButton(
                    action_id="purchaser.select_supplier",
                    label=item.supplier_name,
                    value={"supplier_id": item.supplier_id},
                )
                for item in page.items
            ),
        )

    def supplier_detail(self, supplier: SupplierDetail) -> InteractionView:
        return InteractionView(
            title="供应商详情",
            elements=(
                KeyValueSection(
                    fields=(
                        KeyValueField(label="名称", value=supplier.supplier_name),
                        KeyValueField(label="税号", value=supplier.supplier_tax_number or "-"),
                        KeyValueField(label="开户行", value=supplier.bank_name or "-"),
                        KeyValueField(label="银行账号", value=supplier.bank_account or "-"),
                        KeyValueField(
                            label="黑名单",
                            value="有效"
                            if supplier.blacklist and supplier.blacklist.active
                            else "否",
                        ),
                    )
                ),
            ),
        )

    def warehouse_selection(
        self, detail: RequirementDetail, candidates: HandlerCandidates
    ) -> InteractionView:
        return InteractionView(
            title="选择仓库管理员",
            elements=(
                SelectInput(
                    name="assigned_to_employee_id",
                    label="仓库管理员",
                    options=tuple(
                        SelectOption(label=x.name, value=str(x.employee_id))
                        for x in candidates.items
                    ),
                    required=True,
                ),
            ),
            actions=(
                ActionButton(
                    action_id="purchaser.prepare_submit_warehouse",
                    label="生成确认",
                    value={"requirement_id": detail.requirement_id},
                    style="primary",
                ),
            ),
        )

    def submit_confirmation(
        self, detail: RequirementDetail, employee_id: int, employee_name: str, token: str
    ) -> InteractionView:
        account = detail.purchase_fields.bank_account if detail.purchase_fields else None
        masked = f"****{account[-4:]}" if account and len(account) >= 4 else "-"
        return InteractionView(
            title="确认提交仓库",
            elements=(
                MarkdownBlock(markdown=f"仓库管理员: {employee_name}\n\n银行账号: {masked}"),
            ),
            actions=(
                ActionButton(
                    action_id="purchaser.confirm_submit_warehouse",
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

    def result(self, result: RequirementTransitionResult) -> InteractionView:
        return InteractionView(
            title="已提交仓库",
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
        )
