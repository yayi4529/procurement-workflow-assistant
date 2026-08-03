from decimal import Decimal

from procurement_platform.adapters.backend.dto import (
    BackendAllowedRequirementAction,
    BackendCreatedRequirementDTO,
    BackendCurrentUserDTO,
    BackendFieldsSaveDTO,
    BackendHandlerCandidatesDTO,
    BackendRequirementDetailDTO,
    BackendRequirementMutationDTO,
    BackendRequirementPageDTO,
    BackendSupplierCreatedDTO,
    BackendSupplierDetailDTO,
    BackendSupplierPageDTO,
)
from procurement_platform.domain.enums import AllowedRequirementAction
from procurement_platform.domain.requirement import (
    ApplicantFields,
    FieldsSaveResult,
    HandlerCandidate,
    HandlerCandidates,
    PurchaseFields,
    RequirementBuilding,
    RequirementCompletionResult,
    RequirementDetail,
    RequirementHandler,
    RequirementListItem,
    RequirementPage,
    RequirementSummary,
    RequirementTransitionResult,
    ReviewFields,
    ReviewRecordSummary,
    SupplierBlacklistSummary,
    SupplierDetail,
    SupplierPage,
    SupplierSummary,
    WarehouseFields,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def map_current_user(dto: BackendCurrentUserDTO) -> CurrentUser:
    return CurrentUser(
        employee_id=dto.employee_id,
        name=dto.name,
        mobile=dto.mobile,
        status=dto.status,
        roles=tuple(
            UserRole(role_code=role.role_code, role_name=role.role_name) for role in dto.roles
        ),
        buildings=tuple(
            UserBuilding(
                building_id=building.building_id,
                building_name=building.building_name,
                is_primary=building.is_primary,
            )
            for building in dto.buildings
        ),
    )


def map_created_requirement(dto: BackendCreatedRequirementDTO) -> RequirementSummary:
    return RequirementSummary(
        requirement_id=dto.requirement_id,
        requirement_no=dto.requirement_no,
        status=dto.status,
        version=dto.version,
    )


def map_requirement_detail(dto: BackendRequirementDetailDTO) -> RequirementDetail:
    latest_review = dto.review_records[-1] if dto.review_records else None
    purchase = dto.purchase_execution
    receipt = dto.warehouse_receipt
    return RequirementDetail(
        requirement_id=dto.requirement_id,
        requirement_no=dto.requirement_no,
        status=dto.status,
        version=dto.version,
        building=RequirementBuilding(
            building_id=dto.building.building_id,
            building_name=dto.building.building_name,
        ),
        current_handler=(
            RequirementHandler(
                employee_id=dto.current_handler.employee_id,
                name=dto.current_handler.name,
            )
            if dto.current_handler is not None
            else None
        ),
        applicant_fields=ApplicantFields(**dto.applicant_fields.model_dump(mode="json")),
        review_fields=(
            ReviewFields(
                proposed_supplier_id=latest_review.proposed_supplier_id,
                proposed_supplier_name=latest_review.proposed_supplier_name,
                supplier_contact_name=latest_review.supplier_contact_name,
                supplier_contact_info=latest_review.supplier_contact_info,
                supplier_link=latest_review.supplier_link,
                estimated_unit_price=_decimal_string(latest_review.estimated_unit_price),
                estimated_total_price=_decimal_string(latest_review.estimated_total_price),
                need_contract=latest_review.need_contract,
                contract_type=latest_review.contract_type,
                payment_method=latest_review.payment_method,
                expected_arrival_date=latest_review.expected_arrival_date,
                warranty_info=latest_review.warranty_info,
                review_remark=latest_review.review_remark,
            )
            if latest_review is not None
            else None
        ),
        review_record=(
            ReviewRecordSummary(review_status=latest_review.review_status)
            if latest_review is not None
            else None
        ),
        purchase_fields=(
            PurchaseFields(
                supplier_id=purchase.supplier_id,
                supplier_tax_number=purchase.supplier_tax_number,
                bank_name=purchase.bank_name,
                bank_account=purchase.bank_account,
                registered_address=purchase.registered_address,
                contract_contact_info=purchase.contract_contact_info,
                actual_unit_price=_decimal_string(purchase.actual_unit_price),
                actual_total_price=_decimal_string(purchase.actual_total_price),
                tax_rate=_decimal_string(purchase.tax_rate),
                purchased_at=purchase.purchased_at,
                purchase_remark=purchase.purchase_remark,
            )
            if purchase is not None
            else None
        ),
        warehouse_fields=(
            WarehouseFields(
                warehouse_location=receipt.warehouse_location,
                received_quantity=_decimal_string(receipt.received_quantity),
                receipt_remark=receipt.receipt_remark,
            )
            if receipt is not None
            else None
        ),
        missing_fields=dto.missing_fields,
        allowed_actions=tuple(_map_allowed_action(action) for action in dto.allowed_actions),
        fields_complete=not dto.missing_fields,
        rejection_reason=(
            latest_review.review_opinion
            if latest_review is not None and latest_review.review_result == "REJECTED"
            else None
        ),
        completed_at=(
            receipt.received_at if dto.status.value == "COMPLETED" and receipt is not None else None
        ),
    )


def _decimal_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def map_requirement_page(dto: BackendRequirementPageDTO) -> RequirementPage:
    return RequirementPage(
        items=tuple(
            RequirementListItem(
                requirement_id=item.requirement_id,
                requirement_no=item.requirement_no,
                device_name=item.device_name,
                status=item.status,
                current_handler_name=item.current_handler_name,
            )
            for item in dto.items
        ),
        page=dto.page,
        page_size=dto.page_size,
        total=dto.total,
    )


def map_handler_candidates(dto: BackendHandlerCandidatesDTO) -> HandlerCandidates:
    return HandlerCandidates(
        items=tuple(
            HandlerCandidate(employee_id=item.employee_id, name=item.name) for item in dto.items
        ),
        auto_selected_employee_id=dto.auto_selected_employee_id,
    )


def map_fields_save(dto: BackendFieldsSaveDTO) -> FieldsSaveResult:
    return FieldsSaveResult(
        requirement_id=dto.requirement_id,
        status=dto.status,
        version=dto.version,
        missing_fields=dto.missing_fields,
        next_missing_field=dto.next_missing_field,
        fields_complete=dto.fields_complete,
    )


def map_supplier_page(dto: BackendSupplierPageDTO) -> SupplierPage:
    return SupplierPage(
        items=tuple(
            SupplierSummary(
                supplier_id=item.supplier_id,
                supplier_name=item.supplier_name,
                supplier_tax_number=item.unified_social_credit_code,
                blacklist=SupplierBlacklistSummary(active=item.blacklist_status == "ACTIVE"),
            )
            for item in dto.items
        ),
        page=dto.page,
        page_size=dto.page_size,
        total=dto.total,
    )


def map_supplier_detail(dto: BackendSupplierDetailDTO) -> SupplierDetail:
    return SupplierDetail(
        supplier_id=dto.supplier_id,
        supplier_name=dto.supplier_name,
        supplier_tax_number=dto.unified_social_credit_code,
        blacklist=SupplierBlacklistSummary(active=dto.blacklist.status == "ACTIVE"),
        bank_name=dto.bank_name,
        bank_account=dto.bank_account,
        bank_account_masked=bool(dto.bank_account and "*" in dto.bank_account),
        registered_address=dto.registered_address,
        contract_contact_info=dto.contract_contact_info,
    )


def map_supplier_created(dto: BackendSupplierCreatedDTO) -> SupplierSummary:
    return SupplierSummary(
        supplier_id=dto.supplier_id,
        supplier_name=dto.supplier_name,
    )


def map_requirement_transition(
    dto: BackendRequirementMutationDTO,
) -> RequirementTransitionResult:
    return RequirementTransitionResult(
        requirement_id=dto.requirement_id,
        requirement_no=dto.requirement_no or str(dto.requirement_id),
        status=dto.status,
        version=dto.version,
        current_handler=(
            RequirementHandler(
                employee_id=dto.current_handler.employee_id,
                name=dto.current_handler.name,
            )
            if dto.current_handler is not None
            else None
        ),
        action_token=dto.action_token,
    )


def map_requirement_completion(
    dto: BackendRequirementMutationDTO,
) -> RequirementCompletionResult:
    if dto.completed_at is None:
        raise ValueError("completed mutation response requires completed_at")
    return RequirementCompletionResult(
        requirement_id=dto.requirement_id,
        requirement_no=dto.requirement_no or str(dto.requirement_id),
        status=dto.status,
        version=dto.version,
        current_handler=(
            RequirementHandler(
                employee_id=dto.current_handler.employee_id,
                name=dto.current_handler.name,
            )
            if dto.current_handler is not None
            else None
        ),
        completed_at=dto.completed_at,
        action_token=dto.action_token,
    )


def _map_allowed_action(
    action: BackendAllowedRequirementAction,
) -> AllowedRequirementAction:
    aliases = {
        BackendAllowedRequirementAction.SAVE_APPLICANT_FIELDS: (
            AllowedRequirementAction.UPDATE_APPLICANT_FIELDS
        ),
        BackendAllowedRequirementAction.SAVE_REVIEW_FIELDS: (
            AllowedRequirementAction.UPDATE_REVIEW_FIELDS
        ),
        BackendAllowedRequirementAction.SAVE_PURCHASE_FIELDS: (
            AllowedRequirementAction.UPDATE_PURCHASE_FIELDS
        ),
        BackendAllowedRequirementAction.SAVE_WAREHOUSE_FIELDS: (
            AllowedRequirementAction.UPDATE_WAREHOUSE_FIELDS
        ),
    }
    if action in aliases:
        return aliases[action]
    return AllowedRequirementAction(action.value)
