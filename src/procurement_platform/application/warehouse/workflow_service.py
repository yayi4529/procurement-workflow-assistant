# ruff: noqa: RUF001

from uuid import UUID, uuid4

from procurement_platform.application.multi_item_presenter import (
    request_has_summary,
    request_is_complete,
)
from procurement_platform.application.warehouse.card_factory import WarehouseCardFactory
from procurement_platform.domain.enums import (
    AllowedRequirementAction,
    RequirementStatus,
    RequirementView,
)
from procurement_platform.domain.errors import (
    BackendApplicationError,
    ConcurrentModificationError,
    DuplicateOperationError,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import InteractionView
from procurement_platform.domain.requirement import (
    AppendReceiptCommand,
    RequirementCompletionResult,
    RequirementDetail,
    WarehouseFieldsPatch,
)
from procurement_platform.ports.backend_client import BackendClient


class WarehouseWorkflowService:
    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._cards = WarehouseCardFactory()

    async def list_pending(self, identity: PlatformIdentity, page: int = 1) -> InteractionView:
        return self._cards.listing(
            await self._backend.list_requirements(
                identity=identity, view=RequirementView.PENDING_FOR_ME, page=page
            )
        )

    async def open_requirement(
        self, identity: PlatformIdentity, requirement_id: int
    ) -> InteractionView:
        return self._cards.detail(await self._detail(identity, requirement_id))

    async def _detail(self, identity: PlatformIdentity, requirement_id: int) -> RequirementDetail:
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        purchase = detail.purchase_fields
        if purchase is None or purchase.supplier_name or purchase.supplier_id is None:
            return detail
        try:
            supplier = await self._backend.get_supplier(
                identity=identity, supplier_id=purchase.supplier_id
            )
        except BackendApplicationError:
            return detail
        return detail.model_copy(
            update={
                "purchase_fields": purchase.model_copy(
                    update={"supplier_name": supplier.supplier_name}
                )
            }
        )

    async def save_warehouse_fields(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: WarehouseFieldsPatch,
    ) -> InteractionView:
        latest = await self._detail(identity, requirement_id)
        if latest.version != expected_version:
            return self._cards.detail(latest, "版本已变化, 请重新填写。")
        result = await self._backend.update_warehouse_fields(
            identity=identity,
            requirement_id=requirement_id,
            expected_version=latest.version,
            fields=fields,
        )
        refreshed = await self._detail(identity, requirement_id)
        notice = "保存成功。"
        if "receipt_remark" in result.missing_fields:
            notice = "实际入库数量少于申请数量, 入库备注必填。"
        return self._cards.detail(refreshed, notice)

    async def append_receipt(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        execution_id: int,
        expected_version: int,
        action_token: UUID,
        warehouse_location: str,
        received_quantity: str,
        receipt_remark: str | None,
    ) -> InteractionView:
        latest = await self._detail(identity, requirement_id)
        if latest.version != expected_version:
            return self._cards.detail(latest, "版本已变化，已刷新最新待入库数量。")
        try:
            await self._backend.append_receipt(
                identity=identity,
                requirement_id=requirement_id,
                command=AppendReceiptCommand(
                    expected_version=latest.version,
                    action_token=action_token,
                    execution_id=execution_id,
                    warehouse_location=warehouse_location,
                    received_quantity=received_quantity,
                    receipt_remark=receipt_remark,
                ),
            )
            return self._cards.detail(
                await self._detail(identity, requirement_id), "本次入库已登记。"
            )
        except DuplicateOperationError:
            return self._cards.detail(
                await self._detail(identity, requirement_id), "该次入库已登记，无需重复操作。"
            )
        except (ConcurrentModificationError, BackendApplicationError) as exc:
            refreshed = await self._detail(identity, requirement_id)
            message = (
                "入库数量超过剩余数量，已刷新最新数据。"
                if isinstance(exc, BackendApplicationError)
                and exc.error_code in {"OVER_RECEIPT", "WAREHOUSE_NOT_REQUIRED"}
                else "数据已变化，已刷新最新待入库数量。"
            )
            return self._cards.detail(refreshed, message)

    async def prepare_complete(
        self, identity: PlatformIdentity, requirement_id: int
    ) -> InteractionView:
        latest = await self._detail(identity, requirement_id)
        if (
            latest.status is not RequirementStatus.PENDING_WAREHOUSE
            or AllowedRequirementAction.COMPLETE not in latest.allowed_actions
            or (request_has_summary(latest) and not request_is_complete(latest))
        ):
            return self._cards.detail(latest, "后端当前字段或状态不允许完成入库。")
        return self._cards.confirmation(latest, str(uuid4()))

    async def confirm_complete(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        action_token: UUID,
    ) -> InteractionView:
        latest = await self._detail(identity, requirement_id)
        if latest.version != expected_version:
            return self._cards.detail(latest, "版本已变化, 请重新确认。")
        try:
            result = await self._backend.complete_requirement(
                identity=identity,
                requirement_id=requirement_id,
                expected_version=latest.version,
                action_token=action_token,
            )
        except (DuplicateOperationError, ConcurrentModificationError):
            refreshed = await self._detail(identity, requirement_id)
            if (
                refreshed.status is not RequirementStatus.COMPLETED
                or refreshed.completed_at is None
            ):
                return self._cards.detail(refreshed, "操作未完成, 已加载后端最新状态。")
            result = RequirementCompletionResult(
                requirement_id=refreshed.requirement_id,
                requirement_no=refreshed.requirement_no,
                status=refreshed.status,
                version=refreshed.version,
                current_handler=refreshed.current_handler,
                completed_at=refreshed.completed_at,
                action_token=action_token,
            )
        return self._cards.result(result)
