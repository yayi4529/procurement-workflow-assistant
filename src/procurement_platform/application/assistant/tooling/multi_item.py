"""Typed multi-item draft capability; formal submission remains card-only."""

# ruff: noqa: RUF001

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import Field, field_validator, model_validator

from procurement_platform.application.applicant.options import DEVICE_PROFESSION_OPTIONS
from procurement_platform.application.assistant.entity_references import parse_asset_reference
from procurement_platform.application.assistant.task_context_service import AgentTaskStateService
from procurement_platform.application.assistant.tooling.common import (
    DraftUpdateResultBase,
    StrictArgs,
    _active_user,
)
from procurement_platform.application.assistant.unit_defaults import default_procurement_unit
from procurement_platform.application.assistant.workflow_state import WorkflowStateService
from procurement_platform.domain.assistant import AssistantToolContext
from procurement_platform.domain.assistant_context import (
    AgentDraftItem,
    MultiItemRequestDraft,
)
from procurement_platform.domain.enums import (
    PurchaseItemKind,
    RequestType,
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.errors import (
    BackendProtocolError,
    BackendTimeoutError,
    BackendUnavailableError,
    ConcurrentModificationError,
    PermissionDeniedError,
    RequirementNotFoundError,
    SessionNotFoundError,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import ApplicantFieldsPatch, RequestItemDraft
from procurement_platform.ports.backend_client import BackendClient


class DraftItemChange(StrictArgs):
    draft_item_id: str | None = Field(default=None, pattern=r"^draft-item-[1-9][0-9]*$")
    item_kind: PurchaseItemKind | None = None
    item_name: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: str | None = None
    unit: str | None = Field(
        default=None,
        min_length=1,
        max_length=30,
        description="根据采购项名称和语境自动选择，不得向需求人追问",
    )
    requires_warehouse: bool | None = None
    equipment_category_id: int | None = Field(default=None, gt=0)
    equipment_model_id: int | None = Field(default=None, gt=0)
    brand: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)
    item_reason: str | None = None
    remark: str | None = None

    @model_validator(mode="after")
    def validate_quantity(self) -> "DraftItemChange":
        if self.quantity is not None:
            try:
                if Decimal(self.quantity) <= 0:
                    raise ValueError("quantity must be positive")
            except InvalidOperation as exc:
                raise ValueError("quantity must be a decimal string") from exc
        return self


class UpdateMultiItemDraftArgs(StrictArgs):
    requirement_id: int | None = Field(default=None, gt=0)
    start_new: bool = False
    operation: Literal["REPLACE", "ADD", "UPDATE", "REMOVE", "HEADER"] = "ADD"
    target_draft_item_id: str | None = Field(default=None, pattern=r"^draft-item-[1-9][0-9]*$")
    request_type: RequestType | None = None
    source_asset_ref: str | None = Field(default=None, max_length=80)
    application_reason: str | None = None
    items: tuple[DraftItemChange, ...] = ()

    @field_validator("requirement_id", mode="before")
    @classmethod
    def normalize_absent_requirement_id(cls, value: object) -> object:
        if isinstance(value, str) and value.strip().casefold() in {"", "none", "null"}:
            return None
        return value


class UpdateMultiItemDraftResult(DraftUpdateResultBase):
    request_type: RequestType | None = None
    source_asset_ref: str | None = None
    items: tuple[AgentDraftItem, ...] = ()


class UpdateMultiItemDraftTool:
    name = "update_multi_item_draft"
    side_effect = "MUTATE"
    description = (
        "Create or edit a typed applicant multi-item draft. Supports REPLACE, ADD, UPDATE, "
        "REMOVE and HEADER; each item keeps a stable draft_item_id. Never submits workflow."
    )
    args_model = UpdateMultiItemDraftArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._tasks = AgentTaskStateService(backend)

    async def execute(
        self, *, args: UpdateMultiItemDraftArgs, context: AssistantToolContext
    ) -> UpdateMultiItemDraftResult:
        try:
            resolved = await _active_user(self._backend, context, RoleCode.APPLICANT)
            if resolved is None:
                return self._result("PERMISSION_DENIED", "当前用户不是有效需求人")
            identity, user = resolved
            try:
                session = await self._backend.get_agent_state(
                    identity=identity, conversation_id=context.conversation_id
                )
            except SessionNotFoundError:
                session = None
            task = AgentTaskStateService.from_session(session)
            workflow = WorkflowStateService.from_session(session)
            workflow_starts_new = (
                workflow is not None
                and workflow.workflow_name == "create-draft"
                and workflow.phase == "save-draft"
            )
            if workflow_starts_new:
                raw_items = workflow.collected_inputs.get("items_json")
                if isinstance(raw_items, str):
                    try:
                        parsed_items = tuple(
                            DraftItemChange.model_validate(item)
                            for item in json.loads(raw_items)
                        )
                    except (TypeError, ValueError, json.JSONDecodeError):
                        parsed_items = ()
                    if parsed_items:
                        # The parser-owned workflow input is authoritative for the user's
                        # device name and quantity. Do not let a stale LLM tool argument
                        # replace it with an item from an earlier turn.
                        args = args.model_copy(
                            update={"items": parsed_items, "operation": "REPLACE"}
                        )
            previous = task.request_draft or MultiItemRequestDraft()
            if args.start_new or workflow_starts_new:
                previous = MultiItemRequestDraft()
            elif (
                session is not None
                and session.purchase_request_id is None
                and any(item.request_item_id is not None for item in previous.items)
            ):
                previous = previous.model_copy(update={"items": ()})
            try:
                items = self._apply_items(previous.items, args)
            except ValueError as exc:
                return self._result("INVALID_ARGUMENTS", str(exc), draft=previous)
            request_type = args.request_type or previous.request_type or RequestType.PURCHASE
            source_ref = (
                args.source_asset_ref
                if "source_asset_ref" in args.model_fields_set
                else previous.source_asset_ref
            )
            reason = (
                args.application_reason
                if "application_reason" in args.model_fields_set
                else previous.application_reason
            )
            source_asset_id = None
            if source_ref:
                try:
                    source_asset_id = parse_asset_reference(source_ref)
                except ValueError:
                    return self._result("INVALID_ARGUMENTS", "资产引用无效", draft=previous)
                await self._backend.get_asset(identity=identity, asset_id=source_asset_id)

            requirement_id = (
                None
                if args.start_new or workflow_starts_new
                else args.requirement_id or context.active_requirement_id
            )
            if requirement_id is None:
                previous = MultiItemRequestDraft()
                items = self._apply_items(previous.items, args)
            if requirement_id is None:
                primary = [item for item in user.buildings if item.is_primary]
                building = (
                    user.buildings[0]
                    if len(user.buildings) == 1
                    else primary[0]
                    if len(primary) == 1
                    else None
                )
                if building is None:
                    return self._result("NEED_MORE_INFORMATION", "请先明确所属楼宇", draft=previous)
                summary = await self._backend.create_requirement(
                    identity=identity, building_id=building.building_id
                )
                requirement_id = summary.requirement_id
            detail = await self._backend.get_requirement(
                identity=identity, requirement_id=requirement_id
            )
            if detail.status not in {RequirementStatus.DRAFT, RequirementStatus.REJECTED}:
                if args.requirement_id is not None:
                    return self._result("INVALID_STATUS", "当前采购单不可编辑", draft=previous)
                summary = await self._backend.create_requirement(
                    identity=identity, building_id=detail.building.building_id
                )
                requirement_id = summary.requirement_id
                detail = await self._backend.get_requirement(
                    identity=identity, requirement_id=requirement_id
                )
                previous = MultiItemRequestDraft()
                items = self._apply_items(previous.items, args)
            applicant_patch: dict[str, str] = {}
            if reason is not None and reason != detail.applicant_fields.application_reason:
                applicant_patch["application_reason"] = reason
            if not detail.applicant_fields.device_profession and items:
                historical_profession = await self._historical_device_profession(
                    identity=identity,
                    item_names=tuple(item.item_name for item in items),
                    current_requirement_id=requirement_id,
                )
                if historical_profession is not None:
                    applicant_patch["device_profession"] = historical_profession
            if applicant_patch:
                await self._backend.update_applicant_fields(
                    identity=identity,
                    requirement_id=requirement_id,
                    expected_version=detail.version,
                    fields=ApplicantFieldsPatch.model_validate(applicant_patch),
                )
                detail = await self._backend.get_requirement(
                    identity=identity, requirement_id=requirement_id
                )
            if args.operation != "HEADER" or args.items:
                if not items:
                    return self._result(
                        "NEED_MORE_INFORMATION", "采购草稿至少需要一个采购项", draft=previous
                    )
                await self._backend.replace_request_items(
                    identity=identity,
                    requirement_id=requirement_id,
                    expected_version=detail.version,
                    request_type=request_type,
                    source_asset_id=source_asset_id,
                    items=tuple(self._to_backend_item(item) for item in items),
                )
                detail = await self._backend.get_requirement(
                    identity=identity, requirement_id=requirement_id
                )
                persisted = tuple(item for item in detail.items if item.is_active)
                if len(persisted) != len(items):
                    # The mutation has already succeeded. Re-read once before reporting an
                    # error so a briefly stale detail response cannot turn a successful write
                    # into a failed workflow (and tempt the caller to repeat the mutation).
                    detail = await self._backend.get_requirement(
                        identity=identity, requirement_id=requirement_id
                    )
                    persisted = tuple(item for item in detail.items if item.is_active)
                if len(persisted) != len(items):
                    return self._result(
                        "INTERNAL_ERROR",
                        "后端返回的采购项数量与草稿不一致",
                        draft=previous,
                    )
                items = tuple(
                    draft_item.model_copy(update={"request_item_id": saved_item.request_item_id})
                    for draft_item, saved_item in zip(items, persisted, strict=True)
                )
            draft = MultiItemRequestDraft(
                request_type=request_type,
                source_asset_ref=source_ref,
                application_reason=reason,
                items=items,
            )
            missing = self._missing(draft)
            await self._tasks.save(
                identity=identity,
                conversation_id=context.conversation_id,
                session=session,
                purchase_request_id=requirement_id,
                task=task.model_copy(
                    update={
                        "active_goal": "MULTI_ITEM_REQUEST",
                        "request_draft": draft,
                        "unresolved": tuple(missing),
                        "pending_confirmation": not missing,
                        "last_observation_capability": self.name,
                    }
                ),
            )
            return UpdateMultiItemDraftResult(
                status="SUCCESS",
                requirement_id=requirement_id,
                requirement_version=detail.version,
                updated_fields=("request_type", "source_asset_ref", "application_reason", "items"),
                updated_values={
                    "request_type": request_type.value if request_type else None,
                    "source_asset_ref": source_ref,
                    "application_reason": reason,
                    "items": str(len(items)),
                },
                missing_fields=tuple(missing),
                next_missing_field=missing[0] if missing else None,
                fields_complete=not missing,
                request_type=request_type,
                source_asset_ref=source_ref,
                items=items,
                user_message=(
                    "多采购项草稿已完整，请在正式确认卡中检查并提交"
                    if not missing
                    else f"下一项请补充: {missing[0]}"
                ),
            )
        except ConcurrentModificationError:
            return self._result("CONCURRENT_MODIFICATION", "版本已变化，请刷新后重试")
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return self._result("BACKEND_UNAVAILABLE", "采购后端暂时不可用")

    @staticmethod
    def _apply_items(
        current: tuple[AgentDraftItem, ...], args: UpdateMultiItemDraftArgs
    ) -> tuple[AgentDraftItem, ...]:
        values = list(current)
        if args.operation == "HEADER":
            return current
        if args.operation == "REMOVE":
            if args.target_draft_item_id is None:
                raise ValueError("删除采购项时必须指定 draft_item_id")
            updated = [item for item in values if item.draft_item_id != args.target_draft_item_id]
            if len(updated) == len(values):
                raise ValueError("指定的采购项不存在")
            return tuple(updated)
        if args.operation == "UPDATE":
            if args.target_draft_item_id is None or len(args.items) != 1:
                raise ValueError("更新采购项时必须指定一个目标和一组修改")
            for index, item in enumerate(values):
                if item.draft_item_id == args.target_draft_item_id:
                    changes = args.items[0].model_dump(
                        exclude={"draft_item_id"}, exclude_unset=True
                    )
                    values[index] = item.model_copy(update=changes)
                    return tuple(values)
            raise ValueError("指定的采购项不存在")
        if not args.items:
            raise ValueError("请提供至少一个采购项")
        if args.operation == "REPLACE":
            values = []
        used = {item.draft_item_id for item in values}
        next_number = max((int(value.rsplit("-", 1)[1]) for value in used), default=0) + 1
        for change in args.items:
            raw = change.model_dump(exclude_none=True)
            if not raw.get("unit"):
                raw["unit"] = default_procurement_unit(
                    change.item_name,
                    change.item_kind,
                )
            draft_id = change.draft_item_id or f"draft-item-{next_number}"
            next_number += 1
            if draft_id in used:
                raise ValueError("draft_item_id 重复")
            used.add(draft_id)
            try:
                values.append(AgentDraftItem.model_validate({**raw, "draft_item_id": draft_id}))
            except ValueError as exc:
                raise ValueError("新增采购项缺少类型、名称或数量") from exc
        return tuple(values)

    @staticmethod
    def _to_backend_item(item: AgentDraftItem) -> RequestItemDraft:
        return RequestItemDraft(
            request_item_id=item.request_item_id,
            item_kind=item.item_kind,
            item_name=item.item_name,
            quantity=item.quantity,
            unit=item.unit,
            requires_warehouse=item.requires_warehouse,
            equipment_category_id=item.equipment_category_id,
            equipment_model_id=item.equipment_model_id,
            brand_snapshot=item.brand,
            model_snapshot=item.model,
            item_reason=item.item_reason,
            remark=item.remark,
        )

    @staticmethod
    def _missing(draft: MultiItemRequestDraft) -> list[str]:
        missing = []
        if draft.request_type is None:
            missing.append("request_type")
        if not draft.application_reason:
            missing.append("application_reason")
        if not draft.items:
            missing.append("items")
        return missing

    async def _historical_device_profession(
        self,
        *,
        identity: PlatformIdentity,
        item_names: tuple[str, ...],
        current_requirement_id: int,
    ) -> str | None:
        profession_stats: dict[str, tuple[int, datetime]] = {}
        visited_requirements: set[int] = {current_requirement_id}
        for item_name in dict.fromkeys(item_names):
            records = await self._backend.list_purchase_records(
                identity=identity,
                device_name=item_name,
                page=1,
                page_size=100,
            )
            for record in records.items:
                if record.requirement_id in visited_requirements:
                    continue
                visited_requirements.add(record.requirement_id)
                profession = record.device_profession
                if not profession:
                    try:
                        historical = await self._backend.get_requirement(
                            identity=identity,
                            requirement_id=record.requirement_id,
                        )
                    except (PermissionDeniedError, RequirementNotFoundError):
                        continue
                    profession = historical.applicant_fields.device_profession
                if profession not in DEVICE_PROFESSION_OPTIONS:
                    continue
                count, latest = profession_stats.get(
                    profession,
                    (0, datetime.min.replace(tzinfo=record.created_at.tzinfo)),
                )
                profession_stats[profession] = (
                    count + 1,
                    max(latest, record.created_at),
                )
        ranked = sorted(
            profession_stats,
            key=lambda profession: profession_stats[profession],
            reverse=True,
        )
        return ranked[0] if ranked else None

    @staticmethod
    def _result(
        status: str, message: str, *, draft: MultiItemRequestDraft | None = None
    ) -> UpdateMultiItemDraftResult:
        return UpdateMultiItemDraftResult(
            status=status,
            user_message=message,
            request_type=draft.request_type if draft else None,
            source_asset_ref=draft.source_asset_ref if draft else None,
            items=draft.items if draft else (),
        )
