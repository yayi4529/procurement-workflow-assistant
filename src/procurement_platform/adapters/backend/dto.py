from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from procurement_platform.domain.enums import (
    AgentConversationStatus,
    PlatformType,
    RequirementStatus,
    ReviewStatus,
    RoleCode,
)

DataT = TypeVar("DataT")


class BackendDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BackendEquipmentCategoryDTO(BackendDTO):
    category_id: int
    parent_category_id: int | None
    category_code: str
    category_name: str
    category_level: int
    description: str | None
    sort_order: int
    status: str


class BackendEquipmentCategoryListDTO(BackendDTO):
    items: tuple[BackendEquipmentCategoryDTO, ...]


class BackendEquipmentModelDTO(BackendDTO):
    model_id: int
    category_id: int
    brand: str | None
    model: str
    model_name: str | None
    specifications: dict[str, object] | None
    default_unit: str | None
    lifecycle_status: str
    remark: str | None


class BackendEquipmentModelPageDTO(BackendDTO):
    items: tuple[BackendEquipmentModelDTO, ...]
    page: int
    page_size: int
    total: int


class BackendAssetBuildingDTO(BackendDTO):
    building_id: int
    building_name: str


class BackendAssetDTO(BackendDTO):
    asset_id: int
    asset_code: str
    asset_name: str
    category_id: int
    model_id: int | None
    building_id: int
    location: str | None
    serial_number: str | None
    status: str
    criticality: str
    commissioned_at: date | None
    warranty_end_at: date | None
    configuration: dict[str, object] | None
    aliases: tuple[str, ...] | None
    redundancy_group: str | None
    redundancy_mode: str | None
    remark: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    category: BackendEquipmentCategoryDTO
    model: BackendEquipmentModelDTO | None
    building: BackendAssetBuildingDTO


class BackendAssetPageDTO(BackendDTO):
    items: tuple[BackendAssetDTO, ...]
    page: int
    page_size: int
    total: int


class BackendAssetComponentDTO(BackendDTO):
    component_id: int
    asset_id: int
    component_name: str
    component_category: str | None
    brand: str | None
    model_or_part_no: str | None
    quantity: Decimal
    unit: str | None
    status: str
    replaceable: bool
    remark: str | None


class BackendRelatedAssetDTO(BackendDTO):
    asset_id: int
    asset_code: str
    asset_name: str
    building_id: int
    location: str | None
    status: str


class BackendAssetRelationDTO(BackendDTO):
    relation_id: int
    source_asset_id: int
    relation_type: str
    target_asset_id: int
    remark: str | None
    status: str
    direction: str
    related_asset: BackendRelatedAssetDTO


class BackendAssetContextDTO(BackendDTO):
    asset: BackendAssetDTO
    components: tuple[BackendAssetComponentDTO, ...]
    relations: tuple[BackendAssetRelationDTO, ...]
    redundancy_peers: tuple[BackendAssetDTO, ...]


class BackendAllowedRequirementAction(StrEnum):
    SAVE_APPLICANT_FIELDS = "SAVE_APPLICANT_FIELDS"
    SUBMIT_REVIEW = "SUBMIT_REVIEW"
    RESUBMIT_REVIEW = "RESUBMIT_REVIEW"
    SAVE_REVIEW_FIELDS = "SAVE_REVIEW_FIELDS"
    REJECT = "REJECT"
    SUBMIT_PURCHASER = "SUBMIT_PURCHASER"
    START_PURCHASE = "START_PURCHASE"
    SAVE_PURCHASE_FIELDS = "SAVE_PURCHASE_FIELDS"
    SUBMIT_WAREHOUSE = "SUBMIT_WAREHOUSE"
    SAVE_WAREHOUSE_FIELDS = "SAVE_WAREHOUSE_FIELDS"
    COMPLETE = "COMPLETE"


class BackendEnvelope(BackendDTO, Generic[DataT]):
    success: bool
    code: str
    message: str
    data: DataT | None
    trace_id: str


class BackendUserRoleDTO(BackendDTO):
    role_id: int
    role_code: RoleCode
    role_name: str


class BackendUserBuildingDTO(BackendDTO):
    building_id: int
    building_name: str
    is_primary: bool


class BackendCurrentUserDTO(BackendDTO):
    employee_id: int
    employee_no: str | None
    name: str
    mobile: str | None
    status: str
    platform_type: PlatformType
    platform_user_id: str
    roles: tuple[BackendUserRoleDTO, ...]
    buildings: tuple[BackendUserBuildingDTO, ...]


class BackendPlatformIdentityDTO(BackendDTO):
    platform_type: PlatformType
    platform_user_id: str


class BackendCurrentHandlerDTO(BackendDTO):
    employee_id: int
    name: str
    platform_identities: tuple[BackendPlatformIdentityDTO, ...] = ()


class BackendCreatedRequirementDTO(BackendDTO):
    requirement_id: int
    requirement_no: str
    status: RequirementStatus
    version: int
    current_handler: BackendCurrentHandlerDTO | None
    completed_at: datetime | None


class BackendRequirementMutationDTO(BackendDTO):
    requirement_id: int
    requirement_no: str | None
    status: RequirementStatus
    version: int
    current_handler: BackendCurrentHandlerDTO | None
    completed_at: datetime | None = None
    action_token: UUID | None = None


class BackendRequirementBuildingDTO(BackendDTO):
    building_id: int
    building_name: str


class BackendRequirementHandlerDTO(BackendDTO):
    employee_id: int
    name: str


class BackendApplicantFieldsDTO(BackendDTO):
    device_profession: str | None
    device_name: str | None
    brand: str | None
    model: str | None
    quantity: Decimal | None
    unit: str | None
    application_reason: str | None
    applicant_remark: str | None


class BackendReviewRecordDTO(BackendDTO):
    review_round: int
    review_status: ReviewStatus
    review_result: str | None
    review_opinion: str | None
    proposed_supplier_id: int | None
    proposed_supplier_name: str | None
    supplier_contact_name: str | None
    supplier_contact_info: str | None
    supplier_link: str | None
    estimated_unit_price: Decimal | None
    estimated_total_price: Decimal | None
    need_contract: bool | None
    contract_type: str | None
    payment_method: str | None
    expected_arrival_date: date | None
    warranty_info: str | None
    review_remark: str | None
    reviewed_at: datetime | None


class BackendPurchaseExecutionDTO(BackendDTO):
    supplier_id: int
    supplier_name: str
    supplier_tax_number: str | None
    bank_name: str | None
    bank_account: str | None
    registered_address: str | None
    contract_contact_info: str | None
    actual_unit_price: Decimal
    actual_total_price: Decimal | None
    tax_rate: Decimal | None
    purchased_at: datetime
    purchase_remark: str | None


class BackendWarehouseReceiptDTO(BackendDTO):
    warehouse_location: str
    received_quantity: Decimal
    receipt_remark: str | None
    received_at: datetime


class BackendRequirementDetailDTO(BackendDTO):
    requirement_id: int
    requirement_no: str
    status: RequirementStatus
    version: int
    building: BackendRequirementBuildingDTO
    current_handler: BackendRequirementHandlerDTO | None
    applicant_fields: BackendApplicantFieldsDTO
    review_records: tuple[BackendReviewRecordDTO, ...]
    purchase_execution: BackendPurchaseExecutionDTO | None
    warehouse_receipt: BackendWarehouseReceiptDTO | None
    missing_fields: tuple[str, ...]
    allowed_actions: tuple[BackendAllowedRequirementAction, ...]


class BackendRequirementListItemDTO(BackendDTO):
    requirement_id: int
    requirement_no: str
    device_name: str | None
    status: RequirementStatus
    current_handler_name: str | None


class BackendRequirementPageDTO(BackendDTO):
    items: tuple[BackendRequirementListItemDTO, ...]
    page: int
    page_size: int
    total: int


class BackendTimelineItemDTO(BackendDTO):
    log_id: int
    action_type: str
    operator_name: str
    operator_role_name: str
    operator_mobile_masked: str | None
    from_status: RequirementStatus | None
    to_status: RequirementStatus | None
    assigned_to_employee_id: int | None
    assigned_to_name: str | None
    assigned_to_mobile_masked: str | None
    operation_summary: str | None
    operated_at: datetime


class BackendTimelineDTO(BackendDTO):
    items: tuple[BackendTimelineItemDTO, ...]


class BackendTimelineContactDTO(BackendDTO):
    employee_name: str
    mobile: str | None


class BackendPurchaseRecordDTO(BackendDTO):
    requirement_id: int
    requirement_no: str
    building_id: int | None = None
    device_profession: str | None = None
    device_name: str | None
    brand: str | None
    model: str | None
    quantity: Decimal | None
    unit: str | None
    status: RequirementStatus
    supplier_id: int | None
    supplier_name: str | None
    actual_total_price: Decimal | None
    purchased_at: datetime | None
    created_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None
    received_at: datetime | None
    completed_at: datetime | None


class BackendPurchaseRecordPageDTO(BackendDTO):
    items: tuple[BackendPurchaseRecordDTO, ...]
    page: int
    page_size: int
    total: int


class BackendProductRecommendationDTO(BackendDTO):
    product_id: int | None = None
    brand: str | None
    model: str | None
    historical_count: int
    last_purchased_at: datetime


class BackendProductRecommendationsDTO(BackendDTO):
    items: tuple[BackendProductRecommendationDTO, ...]


class BackendPurchaseHistoryDTO(BackendDTO):
    requirement_id: int
    device_name: str
    brand: str | None
    model: str | None
    quantity: Decimal
    supplier_id: int
    supplier_name: str
    actual_total_price: Decimal
    purchased_at: datetime
    blacklist_status: str


class BackendPurchaseHistoryRecommendationsDTO(BackendDTO):
    items: tuple[BackendPurchaseHistoryDTO, ...]


class BackendHandlerCandidateDTO(BackendDTO):
    employee_id: int
    name: str
    mobile: str | None


class BackendHandlerCandidatesDTO(BackendDTO):
    items: tuple[BackendHandlerCandidateDTO, ...]
    auto_selected_employee_id: int | None


class BackendFieldsSaveDTO(BackendDTO):
    requirement_id: int
    status: RequirementStatus
    version: int
    missing_fields: tuple[str, ...]
    next_missing_field: str | None = None
    fields_complete: bool


class BackendSupplierSummaryDTO(BackendDTO):
    supplier_id: int
    supplier_name: str
    unified_social_credit_code: str | None
    blacklist_status: str


class BackendSupplierPageDTO(BackendDTO):
    items: tuple[BackendSupplierSummaryDTO, ...]
    page: int
    page_size: int
    total: int


class BackendSupplierRecommendationDTO(BackendDTO):
    supplier_id: int
    supplier_name: str
    historical_purchase_count: int
    last_purchase_at: datetime
    blacklist_status: str


class BackendSupplierRecommendationsDTO(BackendDTO):
    items: tuple[BackendSupplierRecommendationDTO, ...]


class BackendSupplierBlacklistDTO(BackendDTO):
    status: str
    history_count: int


class BackendSupplierDetailDTO(BackendDTO):
    supplier_id: int
    supplier_name: str
    unified_social_credit_code: str | None
    bank_name: str | None
    bank_account: str | None
    registered_address: str | None
    contract_contact_info: str | None
    blacklist: BackendSupplierBlacklistDTO


class BackendSupplierCreatedDTO(BackendDTO):
    supplier_id: int
    supplier_name: str


class BackendAgentConversationDTO(BackendDTO):
    conversation_id: int
    status: AgentConversationStatus
    purchase_request_id: int | None
    redis_state_exists: bool


class BackendAgentMessageDTO(BackendDTO):
    """Message shape returned by the backend conversation endpoint.

    The conversation id is intentionally not repeated in each response item: it
    is already part of the request path and is supplied by the adapter mapper.
    """

    message_id: int
    external_message_id: str | None
    sender_type: str
    content: str
    created_at: datetime


class BackendAgentMessagePageDTO(BackendDTO):
    items: tuple[BackendAgentMessageDTO, ...]
    page: int
    page_size: int
    total: int


class BackendAgentSessionStateDTO(BackendDTO):
    conversation_id: int
    purchase_request_id: int | None = None
    current_action: str
    collected_data: dict[str, object]
    missing_fields: tuple[str, ...]
    pending_field: str | None = None
    awaiting_confirmation: bool
    recent_messages: tuple[dict[str, object], ...]
    last_recommendations: tuple[dict[str, object], ...]
    restored_from_snapshot: bool = False


class BackendAgentStateSaveDTO(BackendDTO):
    saved: bool = True
    expires_in_seconds: int


@dataclass(frozen=True, slots=True)
class BackendRawResponse:
    status_code: int
    payload: object
    trace_id: str | None
