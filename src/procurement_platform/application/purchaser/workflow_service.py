# ruff: noqa: RUF001

from uuid import UUID, uuid4

from procurement_platform.application.purchaser.card_factory import PurchaserCardFactory
from procurement_platform.domain.enums import (
    AllowedRequirementAction,
    RequirementStatus,
    RequirementView,
    RoleCode,
)
from procurement_platform.domain.errors import (
    BackendApplicationError,
    ConcurrentModificationError,
    DuplicateOperationError,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import InteractionView
from procurement_platform.domain.requirement import (
    PurchaseFieldsPatch,
    RequirementDetail,
    SupplierPage,
    SupplierUpsertCommand,
)
from procurement_platform.ports.backend_client import BackendClient


class PurchaserWorkflowService:
    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._cards = PurchaserCardFactory()

    async def _detail(self, identity: PlatformIdentity, requirement_id: int) -> RequirementDetail:
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        timeline = await self._backend.get_requirement_timeline(
            identity=identity, requirement_id=requirement_id
        )
        manager = next(
            (
                item
                for item in reversed(timeline.items)
                if item.operator_role_name in {"楼长", "BUILDING_MANAGER"}
            ),
            None,
        )
        manager_contact = (
            await self._backend.get_timeline_contact(
                identity=identity,
                requirement_id=requirement_id,
                log_id=manager.log_id,
                subject="operator",
            )
            if manager
            else None
        )
        return detail.model_copy(
            update={
                "review_manager_name": manager.operator_name if manager else None,
                "review_manager_mobile": manager_contact.mobile if manager_contact else None,
            }
        )

    async def list_pending(self, identity: PlatformIdentity, page: int = 1) -> InteractionView:
        result = await self._backend.list_requirements(
            identity=identity, view=RequirementView.PENDING_FOR_ME, page=page
        )
        return self._cards.listing(result)

    async def open_requirement(
        self, identity: PlatformIdentity, requirement_id: int
    ) -> InteractionView:
        return self._cards.detail(await self._detail(identity, requirement_id))

    async def open_purchase_item(
        self, identity: PlatformIdentity, requirement_id: int, request_item_id: int
    ) -> InteractionView:
        return self._cards.purchase_item_form(
            await self._detail(identity, requirement_id), request_item_id
        )

    async def save_purchase_item(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        request_item_id: int,
        expected_version: int,
        action_token: UUID,
        fields: PurchaseFieldsPatch,
    ) -> InteractionView:
        latest = await self._detail(identity, requirement_id)
        if latest.version != expected_version:
            return self._cards.detail(latest, "版本已变化，请重新填写。")
        try:
            await self._backend.update_purchase_item(
                identity=identity,
                requirement_id=requirement_id,
                request_item_id=request_item_id,
                expected_version=latest.version,
                action_token=action_token,
                fields=fields,
            )
        except DuplicateOperationError:
            pass
        except BackendApplicationError as exc:
            refreshed = await self._detail(identity, requirement_id)
            if exc.error_code == "ITEM_ALREADY_PURCHASED":
                return self._cards.detail(refreshed, "该采购项已经完成采购, 未创建重复执行。")
            raise
        return await self.open_requirement(identity, requirement_id)

    async def start_purchase(
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
            await self._backend.start_purchase(
                identity=identity,
                requirement_id=requirement_id,
                expected_version=latest.version,
                action_token=action_token,
            )
        except (DuplicateOperationError, ConcurrentModificationError):
            pass
        return await self.open_requirement(identity, requirement_id)

    async def search_supplier(
        self, identity: PlatformIdentity, keyword: str, page: int = 1
    ) -> InteractionView:
        return self._cards.supplier_listing(
            await self._backend.search_suppliers(identity=identity, keyword=keyword, page=page)
        )

    def prepare_supplier_search(self) -> InteractionView:
        return self._cards.supplier_search_form()

    def prepare_new_supplier(self) -> InteractionView:
        return self._cards.new_supplier_form()

    async def select_supplier(
        self, identity: PlatformIdentity, supplier_id: int
    ) -> InteractionView:
        return self._cards.supplier_detail(
            await self._backend.get_supplier(identity=identity, supplier_id=supplier_id)
        )

    async def create_supplier(
        self, identity: PlatformIdentity, command: SupplierUpsertCommand
    ) -> InteractionView:
        try:
            supplier = await self._backend.create_supplier(identity=identity, command=command)
        except BackendApplicationError as exc:
            if exc.error_code == "SUPPLIER_MATCH_CONFLICT":
                return self._cards.message(
                    "供应商冲突确认",
                    "后端检测到名称或税号冲突。不会自动合并, 请搜索并确认后端返回的候选。",
                )
            raise
        return self._cards.supplier_listing(
            SupplierPage(items=(supplier,), page=1, page_size=1, total=1)
        )

    async def save_purchase_fields(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: PurchaseFieldsPatch,
    ) -> InteractionView:
        latest = await self._detail(identity, requirement_id)
        if latest.version != expected_version:
            return self._cards.detail(latest, "版本已变化, 请重新填写。")
        await self._backend.update_purchase_fields(
            identity=identity,
            requirement_id=requirement_id,
            expected_version=latest.version,
            fields=fields,
        )
        return await self.open_requirement(identity, requirement_id)

    async def prepare_submit_warehouse(
        self, identity: PlatformIdentity, requirement_id: int, employee_id: int | None
    ) -> InteractionView:
        latest = await self._detail(identity, requirement_id)
        if (
            latest.status is not RequirementStatus.PURCHASING
            or AllowedRequirementAction.SUBMIT_WAREHOUSE not in latest.allowed_actions
            or {value.request_item_id for value in latest.executions}
            != {value.request_item_id for value in latest.items if value.is_active}
        ):
            return self._cards.detail(latest, "后端当前字段或状态不允许提交仓库。")
        active_items = tuple(item for item in latest.items if item.is_active)
        if active_items and not any(item.requires_warehouse for item in active_items):
            return self._cards.service_completion_confirmation(latest, str(uuid4()))
        candidates = await self._backend.list_handler_candidates(
            identity=identity,
            requirement_id=requirement_id,
            target_role=RoleCode.WAREHOUSE_MANAGER,
        )
        selected = next((x for x in candidates.items if x.employee_id == employee_id), None)
        if selected is None and len(candidates.items) == 1:
            selected = candidates.items[0]
        if selected is None:
            return self._cards.warehouse_selection(latest, candidates)
        return self._cards.submit_confirmation(
            latest, selected.employee_id, selected.name, str(uuid4())
        )

    async def confirm_submit_warehouse(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        employee_id: int | None,
        action_token: UUID,
    ) -> InteractionView:
        latest = await self._detail(identity, requirement_id)
        requires_warehouse = any(item.requires_warehouse for item in latest.items if item.is_active)
        if requires_warehouse:
            candidates = await self._backend.list_handler_candidates(
                identity=identity,
                requirement_id=requirement_id,
                target_role=RoleCode.WAREHOUSE_MANAGER,
            )
            if not any(x.employee_id == employee_id for x in candidates.items):
                return self._cards.warehouse_selection(latest, candidates)
        if latest.version != expected_version:
            return self._cards.detail(latest, "版本已变化, 请重新确认。")
        try:
            result = await self._backend.submit_warehouse(
                identity=identity,
                requirement_id=requirement_id,
                expected_version=latest.version,
                assigned_to_employee_id=employee_id,
                action_token=action_token,
            )
        except (DuplicateOperationError, ConcurrentModificationError):
            refreshed = await self._detail(identity, requirement_id)
            if refreshed.status in {
                RequirementStatus.PENDING_WAREHOUSE,
                RequirementStatus.COMPLETED,
            }:
                return self._cards.result(refreshed)
            else:
                return self._cards.detail(refreshed, "操作未完成, 已加载后端最新状态。")
        refreshed = await self._detail(identity, result.requirement_id)
        return self._cards.result(refreshed)
