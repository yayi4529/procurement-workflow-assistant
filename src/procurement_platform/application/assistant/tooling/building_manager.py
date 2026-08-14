"""Building-manager tools for the optional conversational assistant."""

from datetime import date

from pydantic import Field, model_validator

from procurement_platform.application.assistant.candidate_resolver import CandidateResolver
from procurement_platform.application.assistant.tooling.common import (
    DraftUpdateResultBase,
    SessionReferenceStore,
    StrictArgs,
    _active_user,
    _is_handler,
)
from procurement_platform.domain.assistant import AssistantToolContext
from procurement_platform.domain.enums import (
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.errors import (
    ConcurrentModificationError,
    SessionNotFoundError,
)
from procurement_platform.domain.requirement import (
    ReviewFieldsPatch,
)
from procurement_platform.ports.backend_client import BackendClient


class UpdateReviewDraftArgs(StrictArgs):
    requirement_id: int = Field(gt=0, description="待更新的真实采购单 ID。")
    selection_index: int | None = Field(
        default=None, ge=1, description="用户选择最近一次供应商推荐列表中的第几个选项, 从 1 开始。"
    )
    proposed_supplier_ref: str | None = Field(
        default=None,
        max_length=200,
        description="内部精确供应商引用; 自然语言选择推荐项时优先使用 selection_index。",
    )
    supplier_contact_name: str | None = Field(
        default=None, max_length=100, description="用户明确提供的供应商联系人姓名。"
    )
    supplier_contact_info: str | None = Field(
        default=None, max_length=255, description="用户明确提供的供应商联系方式。"
    )
    supplier_link: str | None = Field(
        default=None, max_length=1000, description="用户明确提供的供应商链接。"
    )
    estimated_unit_price: str | None = Field(
        default=None, description="预计采购单价, 使用十进制字符串。"
    )
    need_contract: bool | None = Field(default=None, description="是否需要合同。")
    contract_type: str | None = Field(
        default=None, max_length=100, description="用户明确提供的合同类型。"
    )
    payment_method: str | None = Field(
        default=None, max_length=100, description="用户明确提供的付款方式。"
    )
    expected_arrival_date: date | None = Field(
        default=None, description="明确的预计到货日期, 格式 YYYY-MM-DD; 无法确定时先澄清。"
    )
    warranty_info: str | None = Field(
        default=None, max_length=255, description="用户明确提供的质保信息。"
    )
    review_remark: str | None = Field(default=None, description="用户明确提供的审核备注。")

    @model_validator(mode="after")
    def supplier_source_is_unambiguous(self) -> "UpdateReviewDraftArgs":
        if self.selection_index is not None and self.proposed_supplier_ref:
            raise ValueError("selection_index 与 proposed_supplier_ref 不能同时提供")
        return self


class UpdateReviewDraftResult(DraftUpdateResultBase):
    pass


class UpdateReviewDraftTool:
    name = "update_review_draft"
    side_effect = "MUTATE"
    description = (
        "保存楼长审核草稿, 不执行正式审批、驳回或提交采购员。用户选择最近一次供应商"
        "推荐时使用从 1 开始的 selection_index; proposed_supplier_ref 仅用于内部精确引用。"
        "一条消息包含多个明确字段时可以一次保存。工具会重新校验角色、状态、处理人、"
        "推荐引用和供应商真实性。"
    )
    args_model = UpdateReviewDraftArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)
        self._resolver = CandidateResolver()

    async def execute(
        self, *, args: UpdateReviewDraftArgs, context: AssistantToolContext
    ) -> UpdateReviewDraftResult:
        try:
            resolved = await _active_user(self._backend, context, RoleCode.BUILDING_MANAGER)
            if resolved is None:
                return UpdateReviewDraftResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是有效楼长"
                )
            identity, user = resolved
            detail = await self._backend.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            if detail.status is not RequirementStatus.PENDING_REVIEW:
                return UpdateReviewDraftResult(
                    status="INVALID_STATUS", user_message="当前状态不可保存楼长草稿"
                )
            if not _is_handler(detail, user) or detail.building.building_id not in {
                item.building_id for item in user.buildings
            }:
                return UpdateReviewDraftResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是该采购单处理人"
                )
            raw = args.model_dump(
                exclude={"requirement_id", "selection_index", "proposed_supplier_ref"},
                exclude_unset=True,
            )
            supplier_reference = args.proposed_supplier_ref
            if args.selection_index is not None:
                state = await self._session.state(identity, context.conversation_id)
                recommendations = tuple(
                    item
                    for item in state.last_recommendations
                    if item.kind == "SUPPLIER_RECOMMENDATION"
                )
                if args.selection_index > len(recommendations):
                    return UpdateReviewDraftResult(
                        status="INVALID_ARGUMENTS",
                        user_message="供应商推荐序号不存在, 请重新查询推荐后选择",
                    )
                supplier_reference = recommendations[args.selection_index - 1].reference_id
            if supplier_reference:
                if args.selection_index is None:
                    state = await self._session.state(identity, context.conversation_id)
                supplier_id = self._resolver.resolve(
                    supplier_reference, kind="SUPPLIER_RECOMMENDATION", state=state
                )
                supplier = await self._backend.get_supplier(
                    identity=identity, supplier_id=supplier_id
                )
                if supplier.blacklist and supplier.blacklist.active:
                    return UpdateReviewDraftResult(
                        status="INVALID_STATUS", user_message="该供应商处于有效黑名单"
                    )
                raw.update(
                    {
                        "proposed_supplier_id": supplier.supplier_id,
                        "proposed_supplier_name": supplier.supplier_name,
                    }
                )
            if not raw:
                return UpdateReviewDraftResult(
                    status="NEED_MORE_INFORMATION", user_message="请提供需要保存的审核字段"
                )
            saved = await self._backend.update_review_fields(
                identity=identity,
                requirement_id=args.requirement_id,
                expected_version=detail.version,
                fields=ReviewFieldsPatch.model_validate(raw),
            )
            latest = await self._backend.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            next_missing_field = saved.next_missing_field or (
                saved.missing_fields[0] if saved.missing_fields else None
            )
            await self._session.save(
                identity=identity,
                context=context,
                requirement_id=args.requirement_id,
                focused_role=RoleCode.BUILDING_MANAGER,
                focused_field=next_missing_field,
                missing_fields=saved.missing_fields,
                pending_field=next_missing_field,
            )
            return UpdateReviewDraftResult(
                status="SUCCESS",
                requirement_id=args.requirement_id,
                requirement_version=latest.version,
                updated_fields=tuple(raw),
                updated_values={
                    name: value.isoformat() if isinstance(value, date) else str(value)
                    for name, value in raw.items()
                },
                missing_fields=saved.missing_fields,
                next_missing_field=next_missing_field,
                fields_complete=saved.fields_complete,
            )
        except SessionNotFoundError:
            return UpdateReviewDraftResult(
                status="INVALID_ARGUMENTS",
                user_message="当前没有可用的供应商推荐, 请先重新查询推荐",
            )
        except ValueError as exc:
            return UpdateReviewDraftResult(status="INVALID_ARGUMENTS", user_message=str(exc))
        except ConcurrentModificationError:
            return UpdateReviewDraftResult(
                status="CONCURRENT_MODIFICATION", user_message="版本已变化, 请重新确认"
            )
