"""Warehouse tools for the optional conversational assistant."""

from decimal import Decimal, InvalidOperation

from pydantic import Field

from procurement_platform.application.assistant.tooling.common import (
    DraftUpdateResultBase,
    SessionReferenceStore,
    StrictArgs,
    _active_user,
    _is_handler,
)
from procurement_platform.domain.assistant import AssistantToolContext
from procurement_platform.domain.assistant_session import (
    JsonValue,
)
from procurement_platform.domain.enums import (
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.errors import (
    ConcurrentModificationError,
    SessionNotFoundError,
)
from procurement_platform.domain.requirement import (
    WarehouseFieldsPatch,
)
from procurement_platform.ports.backend_client import BackendClient


class UpdateWarehouseReceiptDraftArgs(StrictArgs):
    requirement_id: int = Field(gt=0)
    received_quantity: str | None = None
    warehouse_location: str | None = Field(default=None, max_length=255)
    receipt_remark: str | None = None


class UpdateWarehouseReceiptDraftResult(DraftUpdateResultBase):
    pass


class UpdateWarehouseReceiptDraftTool:
    name = "update_warehouse_receipt_draft"
    side_effect = "MUTATE"
    description = "Save warehouse receipt draft fields without completing the requirement."
    args_model = UpdateWarehouseReceiptDraftArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)

    async def execute(
        self, *, args: UpdateWarehouseReceiptDraftArgs, context: AssistantToolContext
    ) -> UpdateWarehouseReceiptDraftResult:
        resolved = await _active_user(self._backend, context, RoleCode.WAREHOUSE_MANAGER)
        if resolved is None:
            return UpdateWarehouseReceiptDraftResult(
                status="PERMISSION_DENIED", user_message="当前用户不是有效仓库管理员"
            )
        identity, user = resolved
        try:
            detail = await self._backend.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            if detail.status is not RequirementStatus.PENDING_WAREHOUSE:
                return UpdateWarehouseReceiptDraftResult(
                    status="INVALID_STATUS", user_message="当前状态不可保存入库草稿"
                )
            if not _is_handler(detail, user):
                return UpdateWarehouseReceiptDraftResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是该采购单处理人"
                )
            raw = args.model_dump(exclude={"requirement_id"}, exclude_unset=True)
            if not raw:
                return UpdateWarehouseReceiptDraftResult(
                    status="NEED_MORE_INFORMATION", user_message="请提供需要保存的入库字段"
                )
            if args.received_quantity is not None:
                try:
                    Decimal(args.received_quantity)
                except InvalidOperation:
                    return UpdateWarehouseReceiptDraftResult(
                        status="INVALID_ARGUMENTS", user_message="实收数量格式无效"
                    )
            try:
                patch = WarehouseFieldsPatch.model_validate(raw)
            except ValueError:
                return UpdateWarehouseReceiptDraftResult(
                    status="INVALID_ARGUMENTS", user_message="实收数量格式无效"
                )
            saved = await self._backend.update_warehouse_fields(
                identity=identity,
                requirement_id=args.requirement_id,
                expected_version=detail.version,
                fields=patch,
            )
            latest = await self._backend.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            next_missing_field = saved.missing_fields[0] if saved.missing_fields else None
            warehouse = latest.warehouse_fields
            updated_values = (
                {
                    name: str(getattr(warehouse, name))
                    if getattr(warehouse, name) is not None
                    else None
                    for name in raw
                }
                if warehouse is not None
                else {}
            )
            session_values: dict[str, JsonValue] = dict(updated_values)
            try:
                await self._session.save(
                    identity=identity,
                    context=context,
                    requirement_id=args.requirement_id,
                    focused_role=RoleCode.WAREHOUSE_MANAGER,
                    focused_field=next_missing_field,
                    missing_fields=saved.missing_fields,
                    pending_field=next_missing_field,
                    collected_data=session_values,
                    awaiting_confirmation=saved.fields_complete,
                )
            except SessionNotFoundError:
                pass
            return UpdateWarehouseReceiptDraftResult(
                status="SUCCESS",
                requirement_id=args.requirement_id,
                requirement_version=latest.version,
                updated_fields=tuple(raw),
                updated_values=updated_values,
                missing_fields=saved.missing_fields,
                next_missing_field=next_missing_field,
                fields_complete=saved.fields_complete,
            )
        except ConcurrentModificationError:
            return UpdateWarehouseReceiptDraftResult(
                status="CONCURRENT_MODIFICATION", user_message="版本已变化, 请重新确认"
            )
