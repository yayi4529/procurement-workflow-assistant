from procurement_platform.application.applicant.options import DEVICE_PROFESSION_OPTIONS
from procurement_platform.application.card_values import quantity_text
from procurement_platform.application.status_labels import requirement_status_label
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
    PurchaseRecord,
    RequirementDetail,
    RequirementPage,
)
from procurement_platform.domain.user import CurrentUser


class ApplicantCardFactory:
    @staticmethod
    def _application_date(detail: RequirementDetail) -> str:
        return detail.created_at.astimezone().date().isoformat() if detail.created_at else "-"

    def home(self) -> InteractionView:
        return InteractionView(
            title="采购申请",
            elements=(MarkdownBlock(markdown="创建新申请, 或查看已有采购申请。"),),
            actions=(
                ActionButton(
                    action_id="applicant.start_new", label="新建采购申请", style="primary"
                ),
                ActionButton(action_id="applicant.list", label="我的申请"),
            ),
        )

    def building_selection(self, user: CurrentUser, default: int | None) -> InteractionView:
        return InteractionView(
            title="选择所属楼宇",
            elements=(
                SelectInput(
                    name="building_id",
                    label="所属楼宇",
                    options=tuple(
                        SelectOption(label=item.building_name, value=str(item.building_id))
                        for item in user.buildings
                    ),
                    required=True,
                    default_value=str(default) if default is not None else None,
                ),
            ),
            actions=(
                ActionButton(
                    action_id="applicant.create_draft", label="确认并创建", style="primary"
                ),
            ),
        )

    def message(self, title: str, text: str) -> InteractionView:
        return InteractionView(
            title=title,
            elements=(MarkdownBlock(markdown=text),),
            actions=(ActionButton(action_id="applicant.home", label="返回首页"),),
        )

    def detail(
        self,
        detail: RequirementDetail,
        *,
        notice: str | None = None,
        return_requirement_ids: tuple[int, ...] = (),
    ) -> InteractionView:
        fields = detail.applicant_fields
        editable = detail.status in {RequirementStatus.DRAFT, RequirementStatus.REJECTED}
        elements: list[InteractionElement] = []
        if notice:
            elements.append(MarkdownBlock(markdown=notice))
        summary_fields = [
            KeyValueField(label="采购单编号", value=detail.requirement_no),
            KeyValueField(label="状态", value=requirement_status_label(detail.status)),
            KeyValueField(label="所属楼宇", value=detail.building.building_name),
        ]
        if not editable:
            summary_fields.extend(
                (
                    KeyValueField(label="设备专业", value=fields.device_profession or "-"),
                    KeyValueField(label="设备名称", value=fields.device_name or "-"),
                    KeyValueField(label="品牌", value=fields.brand or "未填写"),
                    KeyValueField(label="型号", value=fields.model or "未填写"),
                    KeyValueField(
                        label="数量和单位",
                        value=f"{quantity_text(fields.quantity)} {fields.unit or ''}".strip(),
                    ),
                    KeyValueField(label="需求原因", value=fields.application_reason or "-"),
                )
            )
        summary_fields.extend(
            (
                KeyValueField(label="申请人", value=detail.applicant_name or "-"),
                KeyValueField(label="申请时间", value=self._application_date(detail)),
            )
        )
        elements.append(KeyValueSection(fields=tuple(summary_fields)))
        if detail.rejection_reason:
            elements.append(MarkdownBlock(markdown=f"**驳回原因:** {detail.rejection_reason}"))
        if editable:
            elements.append(
                SelectInput(
                    name="device_profession",
                    label="设备类型",
                    options=tuple(
                        SelectOption(label=item, value=item) for item in DEVICE_PROFESSION_OPTIONS
                    ),
                    required=True,
                    default_value=(
                        fields.device_profession
                        if fields.device_profession in DEVICE_PROFESSION_OPTIONS
                        else None
                    ),
                )
            )
            specs = (
                ("device_name", "设备名称", fields.device_name, True),
                ("brand", "品牌(选填)", fields.brand, False),
                ("model", "型号(选填)", fields.model, False),
                ("quantity", "数量", quantity_text(fields.quantity, empty=""), True),
                ("unit", "单位", fields.unit, True),
                ("application_reason", "需求原因", fields.application_reason, True),
                ("applicant_remark", "备注(选填)", fields.applicant_remark, False),
            )
            elements.extend(
                TextInput(name=name, label=label, default_value=value, required=required)
                for name, label, value, required in specs
            )
        actions = []
        if editable:
            actions.append(
                ActionButton(
                    action_id=(
                        "applicant.prepare_resubmit"
                        if detail.status is RequirementStatus.REJECTED
                        else "applicant.prepare_submit"
                    ),
                    label="重新提交" if detail.status is RequirementStatus.REJECTED else "准备提交",
                    value={
                        "requirement_id": detail.requirement_id,
                        "expected_version": detail.version,
                    },
                    style="primary",
                )
            )
        if return_requirement_ids:
            actions.append(
                ActionButton(
                    action_id="applicant.history_back",
                    label="返回",
                    value={"requirement_ids": list(return_requirement_ids)},
                )
            )
        else:
            actions.append(ActionButton(action_id="applicant.list", label="我的申请"))
        return InteractionView(
            title="采购申请详情", elements=tuple(elements), actions=tuple(actions)
        )

    def handler_selection(
        self, detail: RequirementDetail, candidates: HandlerCandidates, *, resubmit: bool
    ) -> InteractionView:
        return InteractionView(
            title="选择审批楼长",
            elements=(
                SelectInput(
                    name="assigned_to_employee_id",
                    label="审批楼长",
                    options=tuple(
                        SelectOption(label=item.name, value=str(item.employee_id))
                        for item in candidates.items
                    ),
                    required=True,
                    default_value=(
                        str(candidates.auto_selected_employee_id)
                        if candidates.auto_selected_employee_id is not None
                        else None
                    ),
                ),
            ),
            actions=(
                ActionButton(
                    action_id="applicant.confirm_handler",
                    label="下一步",
                    value={"requirement_id": detail.requirement_id, "resubmit": resubmit},
                    style="primary",
                ),
            ),
        )

    def confirmation(
        self,
        detail: RequirementDetail,
        manager_id: int,
        manager_name: str,
        token: str,
        *,
        resubmit: bool,
    ) -> InteractionView:
        fields = detail.applicant_fields
        return InteractionView(
            title="重新提交确认" if resubmit else "提交审批确认",
            elements=(
                KeyValueSection(
                    fields=(
                        KeyValueField(label="采购单编号", value=detail.requirement_no),
                        KeyValueField(label="所属楼宇", value=detail.building.building_name),
                        KeyValueField(label="设备专业", value=fields.device_profession or "-"),
                        KeyValueField(label="设备名称", value=fields.device_name or "-"),
                        KeyValueField(label="品牌", value=fields.brand or "未填写"),
                        KeyValueField(label="型号", value=fields.model or "未填写"),
                        KeyValueField(
                            label="数量和单位",
                            value=f"{quantity_text(fields.quantity)} {fields.unit or ''}".strip(),
                        ),
                        KeyValueField(label="需求原因", value=fields.application_reason or "-"),
                        KeyValueField(label="审批楼长", value=manager_name),
                        KeyValueField(label="申请人", value=detail.applicant_name or "-"),
                        KeyValueField(label="申请时间", value=self._application_date(detail)),
                    )
                ),
            ),
            actions=(
                ActionButton(
                    action_id=(
                        "applicant.confirm_resubmit" if resubmit else "applicant.confirm_submit"
                    ),
                    label="确认提交",
                    value={
                        "requirement_id": detail.requirement_id,
                        "expected_version": detail.version,
                        "assigned_to_employee_id": manager_id,
                        "action_token": token,
                    },
                    style="primary",
                ),
                ActionButton(
                    action_id="applicant.open",
                    label="返回修改",
                    value={"requirement_id": detail.requirement_id},
                ),
            ),
        )

    def success(self, detail: RequirementDetail) -> InteractionView:
        fields = detail.applicant_fields
        return InteractionView(
            title="提交成功",
            elements=(
                KeyValueSection(
                    fields=(
                        KeyValueField(label="采购单编号", value=detail.requirement_no),
                        KeyValueField(label="所属楼宇", value=detail.building.building_name),
                        KeyValueField(label="设备专业", value=fields.device_profession or "-"),
                        KeyValueField(label="设备名称", value=fields.device_name or "-"),
                        KeyValueField(label="品牌", value=fields.brand or "未填写"),
                        KeyValueField(label="型号", value=fields.model or "未填写"),
                        KeyValueField(
                            label="数量和单位",
                            value=f"{quantity_text(fields.quantity)} {fields.unit or ''}".strip(),
                        ),
                        KeyValueField(label="需求原因", value=fields.application_reason or "-"),
                        KeyValueField(
                            label="审批楼长",
                            value=detail.current_handler.name if detail.current_handler else "-",
                        ),
                        KeyValueField(label="状态", value=requirement_status_label(detail.status)),
                        KeyValueField(
                            label="当前处理人",
                            value=detail.current_handler.name if detail.current_handler else "-",
                        ),
                        KeyValueField(label="申请人", value=detail.applicant_name or "-"),
                        KeyValueField(label="申请时间", value=self._application_date(detail)),
                    )
                ),
            ),
            actions=(
                ActionButton(
                    action_id="applicant.open",
                    label="查看详情",
                    value={"requirement_id": detail.requirement_id},
                ),
                ActionButton(action_id="applicant.list", label="我的申请"),
            ),
        )

    def listing(self, page: RequirementPage) -> InteractionView:
        lines = [
            f"- {item.requirement_no} | {item.device_name or '未填写'} | "
            f"{requirement_status_label(item.status)}"
            for item in page.items
        ]
        actions = [
            ActionButton(
                action_id="applicant.open",
                label=item.requirement_no,
                value={"requirement_id": item.requirement_id},
            )
            for item in page.items
        ]
        if page.page > 1:
            actions.append(
                ActionButton(
                    action_id="applicant.list",
                    label="上一页",
                    value={"page": page.page - 1},
                )
            )
        if page.page * page.page_size < page.total:
            actions.append(
                ActionButton(
                    action_id="applicant.list",
                    label="下一页",
                    value={"page": page.page + 1},
                )
            )
        return InteractionView(
            title="我的采购申请",
            elements=(MarkdownBlock(markdown="\n".join(lines) if lines else "暂无申请"),),
            actions=tuple(actions),
        )

    def history_listing(self, records: tuple[PurchaseRecord, ...]) -> InteractionView:
        ids = [item.requirement_id for item in records]
        lines = ["根据刚才的查询结果, 为您匹配到以下采购需求:", ""]
        lines.extend(
            f"- {item.requirement_no} | {item.device_name or '未填写'} | "
            f"{requirement_status_label(item.status)}"
            for item in records
        )
        lines.extend(("", f"共 **{len(records)}** 条采购申请"))
        return InteractionView(
            title="我的采购申请",
            subtitle="实时查询结果",
            elements=(MarkdownBlock(markdown="\n".join(lines)),),
            actions=tuple(
                ActionButton(
                    action_id="applicant.open",
                    label=f"查看 {item.requirement_no}",
                    value={
                        "requirement_id": item.requirement_id,
                        "return_requirement_ids": ids,
                    },
                )
                for item in records
            ),
        )
