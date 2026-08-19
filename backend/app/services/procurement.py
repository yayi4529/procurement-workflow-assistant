from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.domain.enums import PurchaseItemKind, PurchaseStatus, ReviewStatus, RoleCode
from app.domain.identity import CurrentUser
from app.domain.workflow import WorkflowCommand
from app.models.assets import Asset, EquipmentModel
from app.models.notification import NotificationOutbox
from app.models.procurement import (
    PurchaseExecution,
    PurchaseOperationLog,
    PurchaseRequest,
    PurchaseRequestItem,
    PurchaseReview,
    PurchaseReviewItem,
    Supplier,
    SupplierBlacklist,
    WarehouseReceipt,
)
from app.repositories.procurement import ProcurementRepository
from app.repositories.suppliers import effective_blacklist_condition
from app.schemas.procurement import (
    AppendReceiptRequest,
    ApplicantFields,
    PurchaseFields,
    ReplaceRequestItemsRequest,
    RequirementDetailData,
    RequirementListData,
    RequirementListItem,
    ReviewFields,
    SaveReviewItemsRequest,
    WarehouseFields,
)
from app.services.fulfillment import ProcurementFulfillmentService
from app.services.permissions import require_any_role, require_building_membership
from app.services.privacy import mask_bank_account
from app.services.workflow import WorkflowService

APPLICANT_REQUIRED_FIELDS = (
    "device_profession",
    "device_name",
    "quantity",
    "unit",
    "application_reason",
)
REVIEW_REQUIRED_FIELDS = (
    "estimated_unit_price",
    "payment_method",
    "expected_arrival_date",
    "warranty_info",
)


class ProcurementService:
    def __init__(
        self,
        repository: ProcurementRepository | None = None,
        workflow: WorkflowService | None = None,
    ) -> None:
        self.repository = repository or ProcurementRepository()
        self.workflow = workflow or WorkflowService()
        self.fulfillment = ProcurementFulfillmentService()

    async def replace_request_items(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        request_id: int,
        payload: ReplaceRequestItemsRequest,
    ) -> PurchaseRequest:
        request = await self._get_request(session, request_id)
        if request.status not in {PurchaseStatus.DRAFT.value, PurchaseStatus.REJECTED.value}:
            raise AppError("INVALID_STATUS", "当前状态不允许编辑采购项", 409)
        if request.applicant_employee_id != current_user.employee_id:
            raise AppError("PERMISSION_DENIED", "只能编辑本人发起的采购申请", 403)
        require_any_role(current_user, RoleCode.APPLICANT.value)
        if request.version != payload.expected_version:
            raise AppError("CONCURRENT_MODIFICATION", "采购申请版本已变化", 409)
        if payload.source_asset_id is not None:
            asset = await session.get(Asset, payload.source_asset_id)
            if asset is None:
                raise AppError("ASSET_NOT_FOUND", "来源资产不存在", 404)
            if asset.building_id != request.building_id and not current_user.has_any_role(
                RoleCode.ADMIN.value
            ):
                raise AppError("BUILDING_NOT_ALLOWED", "来源资产不属于采购申请楼宇", 403)

        existing = {
            item.request_item_id: item
            for item in await self.repository.list_request_items(
                session, request_id, include_inactive=True
            )
        }
        next_no = max((item.item_no for item in existing.values()), default=0) + 1
        retained: set[int] = set()
        seen_numbers: set[int] = set()
        for item_data in payload.items:
            if item_data.item_kind == PurchaseItemKind.SERVICE and item_data.requires_warehouse:
                raise AppError("VALIDATION_ERROR", "服务类采购项不能要求入库", 422)
            if item_data.equipment_model_id is not None:
                model = await session.get(EquipmentModel, item_data.equipment_model_id)
                if model is None:
                    raise AppError("EQUIPMENT_MODEL_NOT_FOUND", "设备型号不存在", 404)
                if (
                    item_data.equipment_category_id is not None
                    and model.category_id != item_data.equipment_category_id
                ):
                    raise AppError("MODEL_CATEGORY_MISMATCH", "设备型号与分类不一致", 422)
            if item_data.request_item_id is None:
                item_no = item_data.item_no or next_no
                next_no = max(next_no, item_no + 1)
                item = PurchaseRequestItem(request_id=request_id, item_no=item_no)
                session.add(item)
            else:
                item = existing.get(item_data.request_item_id)
                if item is None:
                    raise AppError("REQUEST_ITEM_NOT_FOUND", "采购项不存在或不属于该申请", 404)
                retained.add(item.request_item_id)
                item_no = item.item_no
                if item_data.item_no is not None and item_data.item_no != item_no:
                    raise AppError("VALIDATION_ERROR", "已持久化采购项的 item_no 不可修改", 422)
            if item_no in seen_numbers:
                raise AppError("VALIDATION_ERROR", "采购项 item_no 不得重复", 422)
            seen_numbers.add(item_no)
            item.item_kind = item_data.item_kind.value
            item.equipment_category_id = item_data.equipment_category_id
            item.equipment_model_id = item_data.equipment_model_id
            item.item_name = item_data.item_name.strip()
            item.brand_snapshot = item_data.brand_snapshot
            item.model_snapshot = item_data.model_snapshot
            item.quantity = item_data.quantity
            item.unit = item_data.unit.strip()
            item.requires_warehouse = (
                item_data.requires_warehouse
                if item_data.requires_warehouse is not None
                else item_data.item_kind != PurchaseItemKind.SERVICE
            )
            item.item_reason = item_data.item_reason
            item.remark = item_data.remark
            item.is_active = True
        for item_id, item in existing.items():
            if item_id not in retained:
                item.is_active = False
        values = {}
        if payload.request_type is not None:
            values["request_type"] = payload.request_type.value
        if "source_asset_id" in payload.model_fields_set:
            values["source_asset_id"] = payload.source_asset_id
        updated = await self.repository.bump_version(
            session,
            request_id=request_id,
            expected_version=payload.expected_version,
            allowed_statuses=[PurchaseStatus.DRAFT.value, PurchaseStatus.REJECTED.value],
            values=values,
        )
        if not updated:
            raise AppError("CONCURRENT_MODIFICATION", "采购申请已被其他操作更新", 409)
        for key, value in values.items():
            setattr(request, key, value)
        request.version = payload.expected_version + 1
        await session.flush()
        return request

    async def save_review_items(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        request_id: int,
        payload: SaveReviewItemsRequest,
    ) -> PurchaseRequest:
        request = await self._get_request(session, request_id)
        self._require_current_handler(current_user, request, RoleCode.BUILDING_MANAGER)
        if request.status != PurchaseStatus.PENDING_REVIEW.value:
            raise AppError("INVALID_STATUS", "当前状态不允许保存逐项审核建议", 409)
        if request.version != payload.expected_version:
            raise AppError("CONCURRENT_MODIFICATION", "采购申请版本已变化", 409)
        items = await self.repository.list_request_items(session, request_id)
        item_map = {item.request_item_id: item for item in items}
        if {value.request_item_id for value in payload.items} != set(item_map):
            raise AppError("MISSING_REQUIRED_FIELDS", "必须为每个有效采购项提供一条审核建议", 400)
        review = await self._get_or_create_review(session, request, current_user)
        await self._ensure_review_snapshots(session, request, review)
        existing = {
            value.request_item_id: value
            for value in await self.repository.list_review_items(session, review.review_id)
        }
        for value in payload.items:
            item = item_map[value.request_item_id]
            supplier = None
            if value.proposed_supplier_id is not None:
                supplier = await self.repository.get_supplier(session, value.proposed_supplier_id)
                if supplier is None or not supplier.status:
                    raise AppError("SUPPLIER_NOT_FOUND", "供应商不存在或已停用", 404)
            calculated_total = None
            if value.estimated_unit_price is not None:
                calculated_total = (item.quantity * value.estimated_unit_price).quantize(
                    Decimal("0.01")
                )
                if (
                    value.estimated_total_price is not None
                    and value.estimated_total_price != calculated_total
                ):
                    raise AppError("VALIDATION_ERROR", "预计总价与数量乘以单价不一致", 422)
            elif value.estimated_total_price is not None:
                raise AppError("VALIDATION_ERROR", "填写预计总价前必须填写预计单价", 422)
            review_item = existing.get(item.request_item_id)
            if review_item is None:
                review_item = PurchaseReviewItem(
                    review_id=review.review_id,
                    request_item_id=item.request_item_id,
                    item_kind_snapshot=item.item_kind,
                    item_name_snapshot=item.item_name,
                    quantity_snapshot=item.quantity,
                    unit_snapshot=item.unit,
                    brand_snapshot=item.brand_snapshot,
                    model_snapshot=item.model_snapshot,
                )
                session.add(review_item)
            review_item.proposed_supplier_id = value.proposed_supplier_id
            review_item.proposed_supplier_name_snapshot = (
                supplier.supplier_name if supplier else None
            )
            review_item.supplier_contact_name = value.supplier_contact_name
            review_item.supplier_contact_info = value.supplier_contact_info
            review_item.supplier_link = value.supplier_link
            review_item.estimated_unit_price = value.estimated_unit_price
            review_item.estimated_total_price = calculated_total
            review_item.need_contract = value.need_contract
            review_item.contract_type = value.contract_type
            review_item.payment_method = value.payment_method
            review_item.expected_arrival_date = value.expected_arrival_date
            review_item.warranty_info = value.warranty_info
            review_item.item_remark = value.item_remark
        updated = await self.repository.bump_version(
            session,
            request_id=request_id,
            expected_version=payload.expected_version,
            allowed_statuses=[PurchaseStatus.PENDING_REVIEW.value],
        )
        if not updated:
            raise AppError("CONCURRENT_MODIFICATION", "采购申请已被其他操作更新", 409)
        request.version = payload.expected_version + 1
        await session.flush()
        return request

    async def create_draft(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        building_id: int,
    ) -> PurchaseRequest:
        require_any_role(current_user, RoleCode.APPLICANT.value)
        require_building_membership(current_user, building_id)
        request = PurchaseRequest(
            request_no=f"PR-{datetime.now():%Y%m%d}-{uuid4().hex[:8].upper()}",
            building_id=building_id,
            applicant_employee_id=current_user.employee_id,
            applicant_platform_type_snapshot=current_user.platform_type,
            applicant_platform_user_id_snapshot=current_user.platform_user_id,
            applicant_name_snapshot=current_user.name,
            applicant_mobile_snapshot=current_user.mobile,
            device_profession=None,
            device_name=None,
            quantity=None,
            unit=None,
            application_reason=None,
            status=PurchaseStatus.DRAFT.value,
            current_handler_employee_id=current_user.employee_id,
            version=0,
        )
        session.add(request)
        await session.flush()
        applicant_role = next(
            role for role in current_user.roles if role.role_code == RoleCode.APPLICANT.value
        )
        session.add(
            PurchaseOperationLog(
                request_id=request.request_id,
                operator_employee_id=current_user.employee_id,
                operator_platform_type_snapshot=current_user.platform_type,
                operator_platform_user_id_snapshot=current_user.platform_user_id,
                operator_name_snapshot=current_user.name,
                operator_mobile_snapshot=current_user.mobile,
                operator_role_id_snapshot=applicant_role.role_id,
                operator_role_name_snapshot=applicant_role.role_name,
                assigned_to_employee_id=current_user.employee_id,
                action_token=None,
                action_type="CREATE_DRAFT",
                from_status=None,
                to_status=PurchaseStatus.DRAFT.value,
                operation_summary="创建采购申请草稿",
                operated_at=datetime.now(),
            )
        )
        await session.flush()
        return request

    async def save_applicant_fields(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        request_id: int,
        expected_version: int,
        fields: ApplicantFields,
    ) -> tuple[PurchaseRequest, list[str]]:
        request = await self._get_request(session, request_id)
        applicant_can_edit = (
            current_user.has_any_role(RoleCode.APPLICANT.value)
            and request.applicant_employee_id == current_user.employee_id
            and request.status
            in {
                PurchaseStatus.DRAFT.value,
                PurchaseStatus.REJECTED.value,
            }
        )
        manager_can_edit = (
            current_user.has_any_role(RoleCode.BUILDING_MANAGER.value)
            and request.current_handler_employee_id == current_user.employee_id
            and request.status == PurchaseStatus.PENDING_REVIEW.value
            and request.building_id in current_user.building_ids
        )
        if not applicant_can_edit and not manager_can_edit:
            raise AppError("INVALID_STATUS", "当前状态不允许修改需求人字段", 409)
        if request.version != expected_version:
            raise AppError("CONCURRENT_MODIFICATION", "采购申请版本已变化", 409)

        values = fields.model_dump(exclude_unset=True)
        allowed_statuses = (
            [PurchaseStatus.PENDING_REVIEW.value]
            if manager_can_edit
            else [
                PurchaseStatus.DRAFT.value,
                PurchaseStatus.REJECTED.value,
            ]
        )
        updated = await self.repository.bump_version(
            session,
            request_id=request_id,
            expected_version=expected_version,
            allowed_statuses=allowed_statuses,
            values=values,
        )
        if not updated:
            raise AppError("CONCURRENT_MODIFICATION", "采购申请已被其他操作更新", 409)
        for key, value in values.items():
            setattr(request, key, value)
        legacy_items = await self.repository.list_request_items(session, request_id)
        if len(legacy_items) > 1:
            raise AppError(
                "MULTI_ITEM_NOT_SUPPORTED_BY_LEGACY_ENDPOINT",
                "多采购项申请必须使用采购项接口",
                409,
            )
        if request.device_name and request.quantity and request.unit:
            item = (
                legacy_items[0]
                if legacy_items
                else PurchaseRequestItem(
                    request_id=request_id,
                    item_no=1,
                    item_kind=PurchaseItemKind.EQUIPMENT.value,
                    requires_warehouse=True,
                    is_active=True,
                )
            )
            if not legacy_items:
                session.add(item)
            item.item_name = request.device_name
            item.brand_snapshot = request.brand
            item.model_snapshot = request.model
            item.quantity = request.quantity
            item.unit = request.unit
            item.item_reason = request.application_reason
        request.version = expected_version + 1
        return request, self.applicant_missing_fields(request)

    async def submit_review(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        command: WorkflowCommand,
    ):
        request = await self._get_request(session, command.request_id)
        items = await self.repository.list_request_items(session, request.request_id)
        missing = [] if items else ["items"]
        missing.extend(self._item_missing_fields(items))
        if missing:
            raise AppError(
                "MISSING_REQUIRED_FIELDS",
                f"需求人字段未完成：{', '.join(missing)}",
                400,
            )
        result = await self.workflow.transition(session, current_user, command)
        await self._create_assignment_notification(session, command, "REQUIREMENT_PENDING_REVIEW")
        return result

    async def reject(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        command: WorkflowCommand,
        reason: str,
    ):
        request = await self._get_request(session, command.request_id)
        self._require_current_handler(
            current_user,
            request,
            RoleCode.BUILDING_MANAGER,
        )
        review = await self._get_or_create_review(session, request, current_user)
        await self._ensure_review_snapshots(session, request, review)
        review.review_status = ReviewStatus.COMPLETED.value
        review.review_result = "REJECTED"
        review.review_opinion = reason
        review.reviewed_at = datetime.now()
        return await self.workflow.transition(session, current_user, command)

    async def save_review_fields(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        request_id: int,
        expected_version: int,
        fields: ReviewFields,
    ) -> tuple[PurchaseRequest, list[str]]:
        request = await self._get_request(session, request_id)
        self._require_current_handler(
            current_user,
            request,
            RoleCode.BUILDING_MANAGER,
        )
        if request.status != PurchaseStatus.PENDING_REVIEW.value:
            raise AppError("INVALID_STATUS", "当前状态不允许保存楼长字段", 409)
        if request.version != expected_version:
            raise AppError("CONCURRENT_MODIFICATION", "采购申请版本已变化", 409)

        review = await self._get_or_create_review(session, request, current_user)
        items = await self.repository.list_request_items(session, request_id)
        if len(items) != 1:
            raise AppError(
                "MULTI_ITEM_NOT_SUPPORTED_BY_LEGACY_ENDPOINT",
                "多采购项申请必须使用逐项审核接口",
                409,
            )
        values = fields.model_dump(exclude_unset=True)
        proposed_supplier_name = values.get("proposed_supplier_name")
        if proposed_supplier_name is not None:
            values["proposed_supplier_name"] = proposed_supplier_name.strip()
            values["proposed_supplier_id"] = None
        supplier_id = values.get("proposed_supplier_id")
        if supplier_id is not None:
            supplier = await self.repository.get_supplier(session, supplier_id)
            if supplier is None or not supplier.status:
                raise AppError("SUPPLIER_NOT_FOUND", "供应商不存在或已停用", 404)
            values["proposed_supplier_name"] = supplier.supplier_name

        unit_price = values.get("estimated_unit_price", review.estimated_unit_price)
        supplied_total = values.pop("estimated_total_price", None)
        if unit_price is not None:
            calculated_total = (items[0].quantity * unit_price).quantize(Decimal("0.01"))
            if supplied_total is not None and supplied_total != calculated_total:
                raise AppError("VALIDATION_ERROR", "预计总价与数量乘以单价不一致", 422)
            values["estimated_total_price"] = calculated_total
        elif supplied_total is not None:
            raise AppError("VALIDATION_ERROR", "填写预计总价前必须填写预计单价", 422)

        for key, value in values.items():
            setattr(review, key, value)
        review_items = await self.repository.list_review_items(session, review.review_id)
        review_item = (
            review_items[0]
            if review_items
            else PurchaseReviewItem(
                review_id=review.review_id,
                request_item_id=items[0].request_item_id,
                item_kind_snapshot=items[0].item_kind,
                item_name_snapshot=items[0].item_name,
                quantity_snapshot=items[0].quantity,
                unit_snapshot=items[0].unit,
                brand_snapshot=items[0].brand_snapshot,
                model_snapshot=items[0].model_snapshot,
            )
        )
        if not review_items:
            session.add(review_item)
        review_item.proposed_supplier_id = review.proposed_supplier_id
        review_item.proposed_supplier_name_snapshot = review.proposed_supplier_name
        review_item.supplier_contact_name = review.supplier_contact_name
        review_item.supplier_contact_info = review.supplier_contact_info
        review_item.supplier_link = review.supplier_link
        review_item.estimated_unit_price = review.estimated_unit_price
        review_item.estimated_total_price = review.estimated_total_price
        review_item.need_contract = review.need_contract
        review_item.contract_type = review.contract_type
        review_item.payment_method = review.payment_method
        review_item.expected_arrival_date = review.expected_arrival_date
        review_item.warranty_info = review.warranty_info
        review_item.item_remark = review.review_remark
        updated = await self.repository.bump_version(
            session,
            request_id=request_id,
            expected_version=expected_version,
            allowed_statuses=[PurchaseStatus.PENDING_REVIEW.value],
        )
        if not updated:
            raise AppError("CONCURRENT_MODIFICATION", "采购申请已被其他操作更新", 409)
        request.version = expected_version + 1
        await session.flush()
        return request, self.review_missing_fields(review)

    async def submit_purchaser(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        command: WorkflowCommand,
    ):
        request = await self._get_request(session, command.request_id)
        self._require_current_handler(current_user, request, RoleCode.BUILDING_MANAGER)
        review = await self._get_or_create_review(session, request, current_user)
        await self._ensure_review_snapshots(session, request, review)
        active_items = await self.repository.list_request_items(session, command.request_id)
        review_items = await self.repository.list_review_items(session, review.review_id)
        missing = [] if len(review_items) == len(active_items) else ["review_items"]
        if missing:
            raise AppError(
                "MISSING_REQUIRED_FIELDS",
                f"楼长字段未完成：{', '.join(missing)}",
                400,
            )
        review.review_status = ReviewStatus.COMPLETED.value
        review.review_result = "APPROVED"
        review.reviewed_at = datetime.now()
        result = await self.workflow.transition(session, current_user, command)
        await self._create_assignment_notification(session, command, "REQUIREMENT_PENDING_PURCHASE")
        return result

    async def start_purchase(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        command: WorkflowCommand,
    ):
        return await self.workflow.transition(session, current_user, command)

    async def save_purchase_fields(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        request_id: int,
        expected_version: int,
        fields: PurchaseFields,
    ) -> PurchaseRequest:
        items = await self.repository.list_request_items(session, request_id)
        if len(items) != 1:
            raise AppError(
                "MULTI_ITEM_NOT_SUPPORTED_BY_LEGACY_ENDPOINT",
                "多采购项申请必须使用逐项采购接口",
                409,
            )
        return await self.save_purchase_item(
            session,
            current_user,
            request_id,
            items[0].request_item_id,
            expected_version,
            fields,
            allow_update=True,
        )

    async def save_purchase_item(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        request_id: int,
        request_item_id: int,
        expected_version: int,
        fields: PurchaseFields,
        action_token: str | None = None,
        *,
        allow_update: bool = False,
    ) -> PurchaseRequest:
        request = await self._get_request(session, request_id)
        self._require_current_handler(current_user, request, RoleCode.PURCHASER)
        if request.status != PurchaseStatus.PURCHASING.value:
            raise AppError("INVALID_STATUS", "当前状态不允许保存采购字段", 409)
        if request.version != expected_version:
            raise AppError("CONCURRENT_MODIFICATION", "采购申请版本已变化", 409)
        if action_token is not None:
            duplicate = await session.scalar(
                select(PurchaseOperationLog.log_id).where(
                    PurchaseOperationLog.action_token == action_token
                )
            )
            if duplicate is not None:
                raise AppError("DUPLICATE_OPERATION", "该采购项已经执行", 409)
        supplier = await self._resolve_purchase_supplier(
            session,
            request_id=request_id,
            supplier_id=fields.supplier_id,
        )

        item = await self.repository.get_request_item(session, request_item_id)
        if item is None or item.request_id != request_id:
            raise AppError("REQUEST_ITEM_NOT_FOUND", "采购项不存在或不属于该申请", 404)
        execution = await self.repository.get_execution_by_item(session, request_item_id)
        self.fulfillment.validate_execution_for_item(item, execution)
        if execution is not None and not allow_update:
            raise AppError("ITEM_ALREADY_PURCHASED", "该采购项已经完成采购执行", 409)
        calculated_total = (item.quantity * fields.actual_unit_price).quantize(Decimal("0.01"))
        if fields.actual_total_price is not None and fields.actual_total_price != calculated_total:
            raise AppError("VALIDATION_ERROR", "实际总价与数量乘以单价不一致", 422)

        if execution is None:
            execution = PurchaseExecution(
                request_id=request_id,
                request_item_id=request_item_id,
                purchaser_employee_id=current_user.employee_id,
                purchaser_platform_type_snapshot=current_user.platform_type,
                purchaser_platform_user_id_snapshot=current_user.platform_user_id,
                purchaser_name_snapshot=current_user.name,
                purchaser_mobile_snapshot=current_user.mobile,
                supplier_id=supplier.supplier_id,
                supplier_name_snapshot=supplier.supplier_name,
                supplier_tax_no_snapshot=fields.supplier_tax_number,
                supplier_bank_name_snapshot=fields.bank_name,
                supplier_bank_account_snapshot=fields.bank_account,
                supplier_address_snapshot=fields.registered_address,
                contract_contact_info_snapshot=fields.contract_contact_info,
                actual_unit_price=fields.actual_unit_price,
                purchased_quantity=item.quantity,
                actual_total_price=calculated_total,
                tax_rate=fields.tax_rate,
                purchased_at=self._naive_datetime(fields.purchased_at),
                execution_remark=fields.purchase_remark,
            )
            session.add(execution)
        else:
            execution.supplier_id = supplier.supplier_id
            execution.supplier_name_snapshot = supplier.supplier_name
            execution.supplier_tax_no_snapshot = fields.supplier_tax_number
            execution.supplier_bank_name_snapshot = fields.bank_name
            execution.supplier_bank_account_snapshot = fields.bank_account
            execution.supplier_address_snapshot = fields.registered_address
            execution.contract_contact_info_snapshot = fields.contract_contact_info
            execution.actual_unit_price = fields.actual_unit_price
            execution.actual_total_price = calculated_total
            execution.tax_rate = fields.tax_rate
            execution.purchased_at = self._naive_datetime(fields.purchased_at)
            execution.execution_remark = fields.purchase_remark

        if fields.update_supplier_profile:
            supplier.unified_social_credit_code = fields.supplier_tax_number
            supplier.bank_name = fields.bank_name
            supplier.bank_account = fields.bank_account
            supplier.registered_address = fields.registered_address
            supplier.contract_contact_info = fields.contract_contact_info

        updated = await self.repository.bump_version(
            session,
            request_id=request_id,
            expected_version=expected_version,
            allowed_statuses=[PurchaseStatus.PURCHASING.value],
        )
        if not updated:
            raise AppError("CONCURRENT_MODIFICATION", "采购申请已被其他操作更新", 409)
        request.version = expected_version + 1
        if action_token is not None:
            role = next(
                role for role in current_user.roles if role.role_code == RoleCode.PURCHASER.value
            )
            session.add(
                PurchaseOperationLog(
                    request_id=request_id,
                    operator_employee_id=current_user.employee_id,
                    operator_platform_type_snapshot=current_user.platform_type,
                    operator_platform_user_id_snapshot=current_user.platform_user_id,
                    operator_name_snapshot=current_user.name,
                    operator_mobile_snapshot=current_user.mobile,
                    operator_role_id_snapshot=role.role_id,
                    operator_role_name_snapshot=role.role_name,
                    assigned_to_employee_id=current_user.employee_id,
                    action_token=action_token,
                    action_type="PURCHASE_ITEM",
                    from_status=request.status,
                    to_status=request.status,
                    operation_summary=(
                        f"request_item_id={item.request_item_id}, "
                        f"supplier_id={supplier.supplier_id}"
                    ),
                    operated_at=datetime.now(),
                )
            )
        await session.flush()
        return request

    async def _resolve_purchase_supplier(
        self,
        session: AsyncSession,
        *,
        request_id: int,
        supplier_id: int | None,
    ) -> Supplier:
        if supplier_id is not None:
            supplier = await self.repository.get_supplier(session, supplier_id)
            if supplier is None or not supplier.status:
                raise AppError("SUPPLIER_NOT_FOUND", "供应商不存在或已停用", 404)
            blocked = await session.scalar(
                select(SupplierBlacklist.blacklist_id).where(
                    SupplierBlacklist.supplier_id == supplier_id,
                    effective_blacklist_condition(datetime.now()),
                )
            )
            if blocked is not None:
                raise AppError("SUPPLIER_BLACKLISTED", "该供应商当前处于黑名单", 409)
            return supplier

        review = await self.repository.get_latest_review(session, request_id)
        supplier_name = review.proposed_supplier_name.strip() if review else ""
        if not supplier_name:
            raise AppError("SUPPLIER_NOT_FOUND", "楼长尚未填写供应商名称", 400)
        supplier = await self.repository.get_active_supplier_by_name(session, supplier_name)
        if supplier is None:
            supplier = Supplier(supplier_name=supplier_name, status=True)
            session.add(supplier)
            await session.flush()
        if review is not None:
            review.proposed_supplier_id = supplier.supplier_id
        return supplier

    async def submit_warehouse(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        command: WorkflowCommand,
    ):
        items = await self.repository.list_request_items(session, command.request_id)
        executions = await self.repository.list_executions_by_request(session, command.request_id)
        if not items or not self.fulfillment.all_active_items_executed(items, executions):
            raise AppError("MISSING_REQUIRED_FIELDS", "仍有采购项未完成采购执行", 400)
        requires_warehouse = any(item.requires_warehouse for item in items if item.is_active)
        result = await self.workflow.transition(
            session,
            current_user,
            command,
            to_status_override=(
                PurchaseStatus.PENDING_WAREHOUSE if requires_warehouse else PurchaseStatus.COMPLETED
            ),
        )
        if requires_warehouse:
            await self._create_assignment_notification(
                session, command, "REQUIREMENT_PENDING_WAREHOUSE"
            )
        else:
            await self._create_completion_notifications(session, command)
        return result

    async def save_warehouse_fields(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        request_id: int,
        expected_version: int,
        fields: WarehouseFields,
    ) -> PurchaseRequest:
        items = [
            item
            for item in await self.repository.list_request_items(session, request_id)
            if item.requires_warehouse
        ]
        executions = await self.repository.list_executions_by_request(session, request_id)
        if len(items) != 1 or len(executions) != 1:
            raise AppError(
                "MULTI_ITEM_NOT_SUPPORTED_BY_LEGACY_ENDPOINT",
                "多采购项或分批收货必须使用追加收货接口",
                409,
            )
        receipts = await self.repository.list_receipts_by_execution(
            session, executions[0].execution_id
        )
        if receipts:
            raise AppError(
                "MULTI_ITEM_NOT_SUPPORTED_BY_LEGACY_ENDPOINT",
                "已有收货历史时必须使用追加收货接口",
                409,
            )
        if (
            fields.received_quantity < executions[0].purchased_quantity
            and not fields.receipt_remark
        ):
            raise AppError(
                "VALIDATION_ERROR",
                "入库数量少于采购数量时必须填写入库备注",
                422,
            )
        payload = AppendReceiptRequest(
            expected_version=expected_version,
            action_token=f"legacy-{request_id}-{expected_version}",
            execution_id=executions[0].execution_id,
            warehouse_location=fields.warehouse_location,
            received_quantity=fields.received_quantity,
            receipt_remark=fields.receipt_remark,
        )
        return await self.append_receipt(session, current_user, request_id, payload)

    async def append_receipt(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        request_id: int,
        payload: AppendReceiptRequest,
    ) -> PurchaseRequest:
        request = await self._get_request(session, request_id)
        self._require_current_handler(
            current_user,
            request,
            RoleCode.WAREHOUSE_MANAGER,
        )
        if request.status != PurchaseStatus.PENDING_WAREHOUSE.value:
            raise AppError("INVALID_STATUS", "当前状态不允许保存入库字段", 409)
        if request.version != payload.expected_version:
            raise AppError("CONCURRENT_MODIFICATION", "采购申请版本已变化", 409)
        duplicate = await session.scalar(
            select(PurchaseOperationLog.log_id).where(
                PurchaseOperationLog.action_token == payload.action_token
            )
        )
        if duplicate is not None:
            raise AppError("DUPLICATE_OPERATION", "该收货操作已经执行", 409)
        execution = await session.get(PurchaseExecution, payload.execution_id, with_for_update=True)
        if execution is None or execution.request_id != request_id:
            raise AppError("PURCHASE_EXECUTION_NOT_FOUND", "采购执行不存在或不属于该申请", 404)
        item = await self.repository.get_request_item(session, execution.request_item_id)
        if item is None:
            raise AppError("FULFILLMENT_INVARIANT_VIOLATION", "采购执行缺少采购项", 500)
        received_total = Decimal(
            await self.repository.get_received_total(session, execution.execution_id)
        )
        self.fulfillment.validate_receipt_quantity(
            item, execution, received_total, payload.received_quantity
        )
        receipt = WarehouseReceipt(
            request_id=request_id,
            execution_id=execution.execution_id,
            warehouse_employee_id=current_user.employee_id,
            warehouse_platform_type_snapshot=current_user.platform_type,
            warehouse_platform_user_id_snapshot=current_user.platform_user_id,
            warehouse_name_snapshot=current_user.name,
            warehouse_mobile_snapshot=current_user.mobile,
            warehouse_location=payload.warehouse_location,
            received_quantity=payload.received_quantity,
            receipt_remark=payload.receipt_remark,
            received_at=datetime.now(),
        )
        session.add(receipt)

        updated = await self.repository.bump_version(
            session,
            request_id=request_id,
            expected_version=payload.expected_version,
            allowed_statuses=[PurchaseStatus.PENDING_WAREHOUSE.value],
        )
        if not updated:
            raise AppError("CONCURRENT_MODIFICATION", "采购申请已被其他操作更新", 409)
        request.version = payload.expected_version + 1
        role = next(
            role
            for role in current_user.roles
            if role.role_code == RoleCode.WAREHOUSE_MANAGER.value
        )
        session.add(
            PurchaseOperationLog(
                request_id=request_id,
                operator_employee_id=current_user.employee_id,
                operator_platform_type_snapshot=current_user.platform_type,
                operator_platform_user_id_snapshot=current_user.platform_user_id,
                operator_name_snapshot=current_user.name,
                operator_mobile_snapshot=current_user.mobile,
                operator_role_id_snapshot=role.role_id,
                operator_role_name_snapshot=role.role_name,
                assigned_to_employee_id=current_user.employee_id,
                action_token=payload.action_token,
                action_type="APPEND_RECEIPT",
                from_status=request.status,
                to_status=request.status,
                operation_summary=(
                    f"execution_id={execution.execution_id}, "
                    f"request_item_id={item.request_item_id}, "
                    f"received_quantity={payload.received_quantity}"
                ),
                operated_at=datetime.now(),
            )
        )
        await session.flush()
        return request

    async def complete(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        command: WorkflowCommand,
    ):
        items = await self.repository.list_request_items(session, command.request_id)
        executions = await self.repository.list_executions_by_request(session, command.request_id)
        execution_map = {value.request_item_id: value for value in executions}
        fulfillment = {}
        for item in items:
            execution = execution_map.get(item.request_item_id)
            received = (
                Decimal(await self.repository.get_received_total(session, execution.execution_id))
                if execution
                else Decimal("0")
            )
            fulfillment[item.request_item_id] = self.fulfillment.get_item_fulfillment(
                item, execution, received
            )
        if not self.fulfillment.all_warehouse_items_fulfilled(items, fulfillment):
            raise AppError("MISSING_REQUIRED_FIELDS", "仍有需入库采购项未完成收货", 400)
        result = await self.workflow.transition(session, current_user, command)
        await self._create_completion_notifications(session, command)
        return result

    async def get_detail(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        request_id: int,
    ) -> RequirementDetailData:
        request = await self._get_request(session, request_id)
        can_view = await self.repository.can_view_request(
            session,
            request,
            current_user.employee_id,
            current_user.has_any_role(RoleCode.ADMIN.value),
            current_user.building_ids,
            current_user.has_any_role(RoleCode.BUILDING_MANAGER.value),
        )
        if not can_view:
            raise AppError("PERMISSION_DENIED", "无权查看该采购申请", 403)
        building, handler, reviews, execution, receipt = await self.repository.get_detail_rows(
            session, request_id
        )
        items = await self.repository.list_request_items(session, request_id, include_inactive=True)
        review_items = await self.repository.list_review_items_by_request(session, request_id)
        executions = await self.repository.list_executions_by_request(session, request_id)
        receipts = await self.repository.list_receipts_by_request(session, request_id)
        review_item_map: dict[int, list[PurchaseReviewItem]] = {}
        for value in review_items:
            review_item_map.setdefault(value.review_id, []).append(value)
        execution_map = {value.request_item_id: value for value in executions}
        received_totals: dict[int, Decimal] = {}
        for value in receipts:
            received_totals[value.execution_id] = (
                received_totals.get(value.execution_id, Decimal("0")) + value.received_quantity
            )
        item_data = []
        fulfillment_statuses = []
        for item in items:
            item_execution = execution_map.get(item.request_item_id)
            fulfillment = self.fulfillment.get_item_fulfillment(
                item,
                item_execution,
                received_totals.get(
                    item_execution.execution_id if item_execution else 0, Decimal("0")
                ),
            )
            fulfillment_statuses.append(fulfillment.status.value)
            item_data.append(
                {
                    "request_item_id": item.request_item_id,
                    "item_no": item.item_no,
                    "item_kind": item.item_kind,
                    "equipment_category_id": item.equipment_category_id,
                    "equipment_model_id": item.equipment_model_id,
                    "item_name": item.item_name,
                    "brand_snapshot": item.brand_snapshot,
                    "model_snapshot": item.model_snapshot,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "requires_warehouse": item.requires_warehouse,
                    "item_reason": item.item_reason,
                    "is_active": item.is_active,
                    "remark": item.remark,
                    "fulfillment_status": fulfillment.status.value,
                }
            )
        can_view_bank = current_user.has_any_role(
            RoleCode.PURCHASER.value,
            RoleCode.ADMIN.value,
        )
        execution_data = None
        if execution is not None:
            execution_data = {
                "supplier_id": execution.supplier_id,
                "supplier_name": execution.supplier_name_snapshot,
                "supplier_tax_number": execution.supplier_tax_no_snapshot,
                "bank_name": execution.supplier_bank_name_snapshot,
                "bank_account": (
                    execution.supplier_bank_account_snapshot
                    if can_view_bank
                    else mask_bank_account(execution.supplier_bank_account_snapshot)
                ),
                "registered_address": execution.supplier_address_snapshot,
                "contract_contact_info": execution.contract_contact_info_snapshot,
                "actual_unit_price": execution.actual_unit_price,
                "actual_total_price": execution.actual_total_price,
                "tax_rate": execution.tax_rate,
                "purchased_at": execution.purchased_at,
                "purchase_remark": execution.execution_remark,
            }
        return RequirementDetailData(
            requirement_id=request.request_id,
            requirement_no=request.request_no,
            status=request.status,
            version=request.version,
            building={
                "building_id": request.building_id,
                "building_name": building.building_name if building else None,
            },
            current_handler=(
                {"employee_id": handler.employee_id, "name": handler.name} if handler else None
            ),
            applicant_fields={
                "device_profession": request.device_profession,
                "device_name": request.device_name,
                "brand": request.brand,
                "model": request.model,
                "quantity": request.quantity,
                "unit": request.unit,
                "application_reason": request.application_reason,
                "applicant_remark": request.applicant_remark,
            },
            review_records=[
                {
                    **self._review_dict(review),
                    "items": [
                        {
                            "review_item_id": value.review_item_id,
                            "request_item_id": value.request_item_id,
                            "item_kind_snapshot": value.item_kind_snapshot,
                            "item_name_snapshot": value.item_name_snapshot,
                            "quantity_snapshot": value.quantity_snapshot,
                            "unit_snapshot": value.unit_snapshot,
                            "brand_snapshot": value.brand_snapshot,
                            "model_snapshot": value.model_snapshot,
                            "proposed_supplier_id": value.proposed_supplier_id,
                            "proposed_supplier_name": value.proposed_supplier_name_snapshot,
                            "estimated_unit_price": value.estimated_unit_price,
                            "estimated_total_price": value.estimated_total_price,
                            "expected_arrival_date": value.expected_arrival_date,
                            "item_remark": value.item_remark,
                        }
                        for value in review_item_map.get(review.review_id, [])
                    ],
                }
                for review in reviews
            ],
            purchase_execution=execution_data,
            warehouse_receipt=(
                {
                    "warehouse_location": receipt.warehouse_location,
                    "received_quantity": receipt.received_quantity,
                    "receipt_remark": receipt.receipt_remark,
                    "received_at": receipt.received_at,
                }
                if receipt
                else None
            ),
            request_type=request.request_type,
            source_asset=(
                {
                    "asset_id": source_asset.asset_id,
                    "asset_code": source_asset.asset_code,
                    "asset_name": source_asset.asset_name,
                }
                if request.source_asset_id
                and (source_asset := await session.get(Asset, request.source_asset_id))
                else None
            ),
            items=item_data,
            executions=[
                {
                    "execution_id": value.execution_id,
                    "request_item_id": value.request_item_id,
                    "supplier_id": value.supplier_id,
                    "supplier_name": value.supplier_name_snapshot,
                    "purchased_quantity": value.purchased_quantity,
                    "actual_unit_price": value.actual_unit_price,
                    "actual_total_price": value.actual_total_price,
                    "tax_rate": value.tax_rate,
                    "purchased_at": value.purchased_at,
                    "purchase_remark": value.execution_remark,
                }
                for value in executions
            ],
            receipts=[
                {
                    "receipt_id": value.receipt_id,
                    "execution_id": value.execution_id,
                    "warehouse_location": value.warehouse_location,
                    "received_quantity": value.received_quantity,
                    "receipt_remark": value.receipt_remark,
                    "received_at": value.received_at,
                }
                for value in receipts
            ],
            request_fulfillment={
                "active_item_count": sum(1 for value in items if value.is_active),
                "fulfilled_item_count": sum(
                    1
                    for item, status in zip(items, fulfillment_statuses, strict=True)
                    if item.is_active and status == "FULFILLED"
                ),
                "all_active_items_fulfilled": all(
                    status in {"FULFILLED", "INACTIVE"} for status in fulfillment_statuses
                ),
            },
            missing_fields=self._current_missing_fields(request, reviews, execution, receipt),
            allowed_actions=self._allowed_actions(current_user, request),
        )

    async def list_requirements(
        self,
        session: AsyncSession,
        current_user: CurrentUser,
        *,
        view: str,
        status: str | None,
        page: int,
        page_size: int,
    ) -> RequirementListData:
        if view == "BUILDING_SCOPE":
            require_any_role(
                current_user,
                RoleCode.BUILDING_MANAGER.value,
                RoleCode.ADMIN.value,
            )
        items, total = await self.repository.list_requests(
            session,
            employee_id=current_user.employee_id,
            view=view,
            status=status,
            building_ids=current_user.building_ids,
            page=page,
            page_size=page_size,
        )
        result_items = []
        for item in items:
            handler = await self.repository.get_employee_handler(
                session,
                item.current_handler_employee_id,
            )
            result_items.append(
                RequirementListItem(
                    requirement_id=item.request_id,
                    requirement_no=item.request_no,
                    device_name=item.device_name,
                    status=item.status,
                    current_handler_name=handler[1] if handler else None,
                )
            )
        return RequirementListData(
            items=result_items,
            page=page,
            page_size=page_size,
            total=total,
        )

    @staticmethod
    def applicant_missing_fields(request: PurchaseRequest) -> list[str]:
        return [
            field for field in APPLICANT_REQUIRED_FIELDS if getattr(request, field) in (None, "")
        ]

    @staticmethod
    def _item_missing_fields(items: list[PurchaseRequestItem]) -> list[str]:
        missing = []
        for item in items:
            if not item.item_name.strip() or item.quantity <= 0 or not item.unit.strip():
                missing.append(f"items[{item.item_no}]")
        return missing

    @staticmethod
    def review_missing_fields(review: PurchaseReview) -> list[str]:
        missing = [
            field for field in REVIEW_REQUIRED_FIELDS if getattr(review, field) in (None, "")
        ]
        if review.proposed_supplier_id is None and not review.proposed_supplier_name:
            missing.append("proposed_supplier")
        if review.need_contract and not review.contract_type:
            missing.append("contract_type")
        return missing

    async def _get_request(
        self,
        session: AsyncSession,
        request_id: int,
    ) -> PurchaseRequest:
        request = await self.repository.get_request(session, request_id)
        if request is None:
            raise AppError("REQUIREMENT_NOT_FOUND", "采购申请不存在", 404)
        return request

    @staticmethod
    def _require_current_handler(
        current_user: CurrentUser,
        request: PurchaseRequest,
        role: RoleCode,
    ) -> None:
        require_any_role(current_user, role.value)
        if request.current_handler_employee_id != current_user.employee_id:
            raise AppError("PERMISSION_DENIED", "当前用户不是采购申请处理人", 403)
        if role == RoleCode.BUILDING_MANAGER:
            require_building_membership(current_user, request.building_id)

    async def _get_or_create_review(
        self,
        session: AsyncSession,
        request: PurchaseRequest,
        current_user: CurrentUser,
    ) -> PurchaseReview:
        review = await self.repository.get_active_review(session, request.request_id)
        if review is not None:
            return review
        review = PurchaseReview(
            request_id=request.request_id,
            review_round=await self.repository.next_review_round(
                session,
                request.request_id,
            ),
            review_status=ReviewStatus.DRAFT.value,
            reviewer_employee_id=current_user.employee_id,
            reviewer_platform_type_snapshot=current_user.platform_type,
            reviewer_platform_user_id_snapshot=current_user.platform_user_id,
            reviewer_name_snapshot=current_user.name,
            reviewer_mobile_snapshot=current_user.mobile,
            need_contract=False,
        )
        session.add(review)
        await session.flush()
        return review

    async def _ensure_review_snapshots(
        self,
        session: AsyncSession,
        request: PurchaseRequest,
        review: PurchaseReview,
    ) -> None:
        items = await self.repository.list_request_items(session, request.request_id)
        existing = {
            value.request_item_id
            for value in await self.repository.list_review_items(session, review.review_id)
        }
        for item in items:
            if item.request_item_id in existing:
                continue
            session.add(
                PurchaseReviewItem(
                    review_id=review.review_id,
                    request_item_id=item.request_item_id,
                    item_kind_snapshot=item.item_kind,
                    item_name_snapshot=item.item_name,
                    quantity_snapshot=item.quantity,
                    unit_snapshot=item.unit,
                    brand_snapshot=item.brand_snapshot,
                    model_snapshot=item.model_snapshot,
                    need_contract=False,
                )
            )
        await session.flush()

    async def _create_completion_notifications(
        self,
        session: AsyncSession,
        command: WorkflowCommand,
    ) -> None:
        request = await self._get_request(session, command.request_id)
        review = await self.repository.get_latest_review(session, command.request_id)
        execution = await self.repository.get_execution(session, command.request_id)
        receiver_ids = {
            request.applicant_employee_id,
            review.reviewer_employee_id if review else None,
            execution.purchaser_employee_id if execution else None,
        }
        for receiver_id in sorted(value for value in receiver_ids if value is not None):
            identities = await self.repository.get_platform_identities(
                session,
                receiver_id,
            )
            identity = self._feishu_identity(identities)
            if identity is None:
                continue
            platform_type, platform_user_id = identity
            session.add(
                NotificationOutbox(
                    request_id=request.request_id,
                    event_type="PROCUREMENT_COMPLETED",
                    receiver_employee_id=receiver_id,
                    platform_type=platform_type,
                    receiver_platform_user_id_snapshot=platform_user_id,
                    dedup_key=f"COMPLETE:{command.action_token}:{receiver_id}",
                    payload={
                        "request_id": request.request_id,
                        "request_no": request.request_no,
                        "status": PurchaseStatus.COMPLETED.value,
                    },
                    status="PENDING",
                    retry_count=0,
                )
            )
        await session.flush()

    async def _create_assignment_notification(
        self,
        session: AsyncSession,
        command: WorkflowCommand,
        event_type: str,
    ) -> None:
        request = await self._get_request(session, command.request_id)
        receiver_id = request.current_handler_employee_id
        if receiver_id is None:
            return
        identities = await self.repository.get_platform_identities(session, receiver_id)
        identity = self._feishu_identity(identities)
        if identity is None:
            return
        platform_type, platform_user_id = identity
        items = await self.repository.list_request_items(session, request.request_id)
        item_summary = "、".join(
            f"{item.item_name}×{item.quantity}{item.unit}" for item in items[:3]
        )
        if len(items) > 3:
            item_summary = f"{item_summary} 等 {len(items)} 项"
        session.add(
            NotificationOutbox(
                request_id=request.request_id,
                event_type=event_type,
                receiver_employee_id=receiver_id,
                platform_type=platform_type,
                receiver_platform_user_id_snapshot=platform_user_id,
                dedup_key=f"{event_type}:{command.action_token}:{receiver_id}",
                payload={
                    "requirement_id": request.request_id,
                    "requirement_no": request.request_no,
                    "status": request.status,
                    "item_count": len(items),
                    "item_summary": item_summary,
                },
                status="PENDING",
                retry_count=0,
            )
        )
        await session.flush()

    @staticmethod
    def _feishu_identity(identities: list[tuple[str, str]]) -> tuple[str, str] | None:
        return next(
            (
                (platform_type, platform_user_id)
                for platform_type, platform_user_id in identities
                if platform_type.upper() == "FEISHU"
            ),
            None,
        )

    @staticmethod
    def _naive_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)

    @staticmethod
    def _review_dict(review: PurchaseReview) -> dict:
        return {
            "review_round": review.review_round,
            "review_status": review.review_status,
            "review_result": review.review_result,
            "review_opinion": review.review_opinion,
            "proposed_supplier_id": review.proposed_supplier_id,
            "proposed_supplier_name": review.proposed_supplier_name,
            "supplier_contact_name": review.supplier_contact_name,
            "supplier_contact_info": review.supplier_contact_info,
            "supplier_link": review.supplier_link,
            "estimated_unit_price": review.estimated_unit_price,
            "estimated_total_price": review.estimated_total_price,
            "need_contract": review.need_contract,
            "contract_type": review.contract_type,
            "payment_method": review.payment_method,
            "expected_arrival_date": review.expected_arrival_date,
            "warranty_info": review.warranty_info,
            "review_remark": review.review_remark,
            "reviewed_at": review.reviewed_at,
        }

    def _current_missing_fields(
        self,
        request: PurchaseRequest,
        reviews: list[PurchaseReview],
        execution: PurchaseExecution | None,
        receipt: WarehouseReceipt | None,
    ) -> list[str]:
        if request.status in {
            PurchaseStatus.DRAFT.value,
            PurchaseStatus.REJECTED.value,
        }:
            return self.applicant_missing_fields(request)
        if request.status == PurchaseStatus.PENDING_REVIEW.value:
            active = next(
                (
                    review
                    for review in reversed(reviews)
                    if review.review_status == ReviewStatus.DRAFT.value
                ),
                None,
            )
            return self.review_missing_fields(active) if active else list(REVIEW_REQUIRED_FIELDS)
        if request.status == PurchaseStatus.PURCHASING.value and execution is None:
            return ["purchase_execution"]
        if request.status == PurchaseStatus.PENDING_WAREHOUSE.value and receipt is None:
            return ["warehouse_receipt"]
        return []

    @staticmethod
    def _allowed_actions(
        current_user: CurrentUser,
        request: PurchaseRequest,
    ) -> list[str]:
        if request.current_handler_employee_id != current_user.employee_id:
            return []
        mapping = {
            PurchaseStatus.DRAFT.value: ("APPLICANT", ["SAVE_APPLICANT_FIELDS", "SUBMIT_REVIEW"]),
            PurchaseStatus.REJECTED.value: (
                "APPLICANT",
                ["SAVE_APPLICANT_FIELDS", "RESUBMIT_REVIEW"],
            ),
            PurchaseStatus.PENDING_REVIEW.value: (
                "BUILDING_MANAGER",
                [
                    "SAVE_APPLICANT_FIELDS",
                    "REJECT",
                    "SAVE_REVIEW_FIELDS",
                    "SUBMIT_PURCHASER",
                ],
            ),
            PurchaseStatus.PENDING_PURCHASE.value: ("PURCHASER", ["START_PURCHASE"]),
            PurchaseStatus.PURCHASING.value: (
                "PURCHASER",
                ["SAVE_PURCHASE_FIELDS", "SUBMIT_WAREHOUSE"],
            ),
            PurchaseStatus.PENDING_WAREHOUSE.value: (
                "WAREHOUSE_MANAGER",
                ["SAVE_WAREHOUSE_FIELDS", "COMPLETE"],
            ),
        }
        required_role, actions = mapping.get(request.status, ("", []))
        return actions if current_user.has_any_role(required_role) else []
