from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from procurement_platform.domain.enums import (
    AllowedRequirementAction,
    RequirementStatus,
    ReviewStatus,
)


class RequirementModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FieldsSaveResult(RequirementModel):
    requirement_id: int
    status: RequirementStatus
    version: int
    missing_fields: tuple[str, ...]
    next_missing_field: str | None = None
    fields_complete: bool


class SupplierBlacklistSummary(RequirementModel):
    active: bool
    reason: str | None = None


class SupplierSummary(RequirementModel):
    supplier_id: int
    supplier_name: str
    supplier_tax_number: str | None = None
    blacklist: SupplierBlacklistSummary | None = None


class SupplierDetail(SupplierSummary):
    bank_name: str | None = None
    bank_account: str | None = None
    bank_account_masked: bool = True
    registered_address: str | None = None
    contract_contact_info: str | None = None

    def __repr__(self) -> str:
        return (
            f"SupplierDetail(supplier_id={self.supplier_id!r}, "
            f"supplier_name={self.supplier_name!r}, bank_account=<sensitive>)"
        )


class SupplierPage(RequirementModel):
    items: tuple[SupplierSummary, ...]
    page: int
    page_size: int
    total: int


class SupplierRecommendation(RequirementModel):
    supplier_id: int
    supplier_name: str
    historical_purchase_count: int
    last_purchase_at: datetime
    blacklist_status: str


class SupplierRecommendations(RequirementModel):
    items: tuple[SupplierRecommendation, ...]


class SupplierUpsertCommand(RequirementModel):
    supplier_name: str
    supplier_tax_number: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    registered_address: str | None = None
    contract_contact_info: str | None = None

    def __repr__(self) -> str:
        return (
            f"SupplierUpsertCommand(supplier_name={self.supplier_name!r}, bank_account=<sensitive>)"
        )


class PurchaseFields(RequirementModel):
    supplier_id: int | None = None
    supplier_name: str | None = None
    supplier_tax_number: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    registered_address: str | None = None
    contract_contact_info: str | None = None
    actual_unit_price: str | None = None
    actual_total_price: str | None = None
    tax_rate: str | None = None
    purchased_at: datetime | None = None
    purchase_remark: str | None = None
    update_supplier_profile: bool = False

    def __repr__(self) -> str:
        return f"PurchaseFields(supplier_id={self.supplier_id!r}, bank_account=<sensitive>)"


class PurchaseFieldsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: int | None = None
    supplier_tax_number: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    registered_address: str | None = None
    contract_contact_info: str | None = None
    actual_unit_price: str | None = None
    actual_total_price: str | None = None
    tax_rate: str | None = None
    purchased_at: datetime | None = None
    purchase_remark: str | None = None
    update_supplier_profile: bool = False

    def provided_fields(self) -> dict[str, object]:
        return self.model_dump(exclude_unset=True)

    def __repr__(self) -> str:
        return "PurchaseFieldsPatch(bank_account=<sensitive>)"


class PurchaseFieldsSaveResult(FieldsSaveResult):
    purchase_fields: PurchaseFields


class PurchaseExecutionSummary(RequirementModel):
    requirement_id: int
    purchase_fields: PurchaseFields
    fields_complete: bool


class WarehouseFields(RequirementModel):
    warehouse_location: str | None = None
    received_quantity: str | None = None
    receipt_remark: str | None = None


class WarehouseFieldsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_location: str | None = None
    received_quantity: str | None = None
    receipt_remark: str | None = None

    @field_validator("received_quantity")
    @classmethod
    def validate_received_quantity(cls, value: str | None) -> str | None:
        if value is not None and Decimal(value) <= 0:
            raise ValueError("received_quantity must be greater than zero")
        return value

    def provided_fields(self) -> dict[str, str | None]:
        return self.model_dump(exclude_unset=True)


class WarehouseFieldsSaveResult(FieldsSaveResult):
    warehouse_fields: WarehouseFields


class WarehouseReceiptSummary(RequirementModel):
    requirement_id: int
    warehouse_fields: WarehouseFields
    fields_complete: bool


class StartPurchaseCommand(RequirementModel):
    expected_version: int
    action_token: UUID


class SubmitWarehouseCommand(StartPurchaseCommand):
    assigned_to_employee_id: int


class RequirementBuilding(RequirementModel):
    building_id: int
    building_name: str


class RequirementHandler(RequirementModel):
    employee_id: int
    name: str


class ApplicantFields(RequirementModel):
    device_profession: str | None = None
    device_name: str | None = None
    brand: str | None = None
    model: str | None = None
    quantity: str | None = None
    unit: str | None = None
    application_reason: str | None = None
    applicant_remark: str | None = None


class ApplicantFieldsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_profession: str | None = None
    device_name: str | None = None
    brand: str | None = None
    model: str | None = None
    quantity: str | None = None
    unit: str | None = None
    application_reason: str | None = None
    applicant_remark: str | None = None

    def provided_fields(self) -> dict[str, str | None]:
        return self.model_dump(exclude_unset=True)


class ReviewFields(RequirementModel):
    proposed_supplier_id: int | None = None
    proposed_supplier_name: str | None = None
    supplier_contact_name: str | None = None
    supplier_contact_info: str | None = None
    supplier_link: str | None = None
    estimated_unit_price: str | None = None
    estimated_total_price: str | None = None
    need_contract: bool | None = None
    contract_type: str | None = None
    payment_method: str | None = None
    expected_arrival_date: date | None = None
    warranty_info: str | None = None
    review_remark: str | None = None


class ReviewFieldsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_supplier_id: int | None = None
    proposed_supplier_name: str | None = None
    supplier_contact_name: str | None = None
    supplier_contact_info: str | None = None
    supplier_link: str | None = None
    estimated_unit_price: str | None = None
    need_contract: bool | None = None
    contract_type: str | None = None
    payment_method: str | None = None
    expected_arrival_date: date | None = None
    warranty_info: str | None = None
    review_remark: str | None = None

    def provided_fields(self) -> dict[str, object]:
        return self.model_dump(exclude_unset=True)


class ReviewRecordSummary(RequirementModel):
    review_status: ReviewStatus


class ReviewFieldsSaveResult(FieldsSaveResult):
    review_fields: ReviewFields
    review_record: ReviewRecordSummary


class RequirementSummary(RequirementModel):
    requirement_id: int
    requirement_no: str
    status: RequirementStatus
    version: int


class RequirementCompletionResult(RequirementSummary):
    current_handler: RequirementHandler | None = None
    completed_at: datetime
    action_token: UUID | None = None


class ApplicantFieldsSaveResult(FieldsSaveResult):
    pass


class RequirementDetail(RequirementSummary):
    building: RequirementBuilding
    current_handler: RequirementHandler | None = None
    applicant_fields: ApplicantFields
    review_fields: ReviewFields | None = None
    review_record: ReviewRecordSummary | None = None
    purchase_fields: PurchaseFields | None = None
    warehouse_fields: WarehouseFields | None = None
    missing_fields: tuple[str, ...]
    allowed_actions: tuple[AllowedRequirementAction, ...]
    fields_complete: bool = False
    rejection_reason: str | None = None
    completed_at: datetime | None = None
    applicant_name: str | None = None
    applicant_mobile: str | None = None
    created_at: datetime | None = None
    review_manager_name: str | None = None
    review_manager_mobile: str | None = None


class RequirementListItem(RequirementModel):
    requirement_id: int
    requirement_no: str
    status: RequirementStatus
    device_name: str | None = None
    current_handler_name: str | None = None


class RequirementPage(RequirementModel):
    items: tuple[RequirementListItem, ...]
    page: int
    page_size: int
    total: int


class TimelineItem(RequirementModel):
    log_id: int
    action_type: str
    operator_name: str
    operator_role_name: str
    operator_mobile_masked: str | None = None
    from_status: RequirementStatus | None = None
    to_status: RequirementStatus | None = None
    assigned_to_employee_id: int | None = None
    assigned_to_name: str | None = None
    assigned_to_mobile_masked: str | None = None
    operation_summary: str | None = None
    operated_at: datetime


class RequirementTimeline(RequirementModel):
    items: tuple[TimelineItem, ...]


class TimelineContact(RequirementModel):
    employee_name: str
    mobile: str | None = None


class PurchaseRecord(RequirementModel):
    requirement_id: int
    requirement_no: str
    building_id: int | None = None
    device_profession: str | None = None
    device_name: str | None = None
    brand: str | None = None
    model: str | None = None
    quantity: str | None = None
    unit: str | None = None
    status: RequirementStatus
    supplier_id: int | None = None
    supplier_name: str | None = None
    actual_total_price: str | None = None
    purchased_at: datetime | None = None
    created_at: datetime
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    received_at: datetime | None = None
    completed_at: datetime | None = None


class PurchaseRecordPage(RequirementModel):
    items: tuple[PurchaseRecord, ...]
    page: int
    page_size: int
    total: int


class ProductRecommendation(RequirementModel):
    product_id: int | None = None
    brand: str | None
    model: str | None
    historical_count: int
    last_purchased_at: datetime


class ProductRecommendations(RequirementModel):
    items: tuple[ProductRecommendation, ...]


class PurchaseHistoryItem(RequirementModel):
    requirement_id: int
    device_name: str
    brand: str | None
    model: str | None
    quantity: str
    supplier_id: int
    supplier_name: str
    actual_total_price: str
    purchased_at: datetime
    blacklist_status: str


class PurchaseHistoryRecommendations(RequirementModel):
    items: tuple[PurchaseHistoryItem, ...]


class HandlerCandidate(RequirementModel):
    employee_id: int
    name: str


class HandlerCandidates(RequirementModel):
    items: tuple[HandlerCandidate, ...]
    auto_selected_employee_id: int | None = None


class RequirementTransitionResult(RequirementSummary):
    current_handler: RequirementHandler | None = None
    action_token: UUID | None = None


class RejectRequirementCommand(RequirementModel):
    expected_version: int
    reason: str
    action_token: UUID


class SubmitPurchaserCommand(RequirementModel):
    expected_version: int
    assigned_to_employee_id: int
    action_token: UUID
