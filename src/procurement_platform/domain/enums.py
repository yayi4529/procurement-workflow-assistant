from enum import StrEnum


class RoleCode(StrEnum):
    APPLICANT = "APPLICANT"
    BUILDING_MANAGER = "BUILDING_MANAGER"
    PURCHASER = "PURCHASER"
    WAREHOUSE_MANAGER = "WAREHOUSE_MANAGER"
    ADMIN = "ADMIN"


class PlatformType(StrEnum):
    FEISHU = "FEISHU"
    DINGTALK = "DINGTALK"
    WECHAT_WORK = "WECHAT_WORK"
    WEB = "WEB"
    TEST_PLATFORM = "TEST_PLATFORM"


class BackendMode(StrEnum):
    HTTP = "http"
    FAKE = "fake"


class AgentConversationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class AgentMessageSender(StrEnum):
    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class RequirementStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    REJECTED = "REJECTED"
    PENDING_PURCHASE = "PENDING_PURCHASE"
    PURCHASING = "PURCHASING"
    PENDING_WAREHOUSE = "PENDING_WAREHOUSE"
    COMPLETED = "COMPLETED"


class RequestType(StrEnum):
    PURCHASE = "PURCHASE"
    MAINTENANCE = "MAINTENANCE"
    FAULT = "FAULT"
    RETIREMENT = "RETIREMENT"


class PurchaseItemKind(StrEnum):
    EQUIPMENT = "EQUIPMENT"
    COMPONENT = "COMPONENT"
    MATERIAL = "MATERIAL"
    SERVICE = "SERVICE"
    TOOL = "TOOL"


class ItemFulfillmentStatus(StrEnum):
    INACTIVE = "INACTIVE"
    PENDING_PURCHASE = "PENDING_PURCHASE"
    PURCHASED = "PURCHASED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    FULFILLED = "FULFILLED"


class RequirementView(StrEnum):
    CREATED_BY_ME = "CREATED_BY_ME"
    PENDING_FOR_ME = "PENDING_FOR_ME"
    PROCESSED_BY_ME = "PROCESSED_BY_ME"


class AllowedRequirementAction(StrEnum):
    UPDATE_APPLICANT_FIELDS = "UPDATE_APPLICANT_FIELDS"
    SUBMIT_REVIEW = "SUBMIT_REVIEW"
    RESUBMIT_REVIEW = "RESUBMIT_REVIEW"
    UPDATE_REVIEW_FIELDS = "UPDATE_REVIEW_FIELDS"
    REJECT = "REJECT"
    SUBMIT_PURCHASER = "SUBMIT_PURCHASER"
    START_PURCHASE = "START_PURCHASE"
    UPDATE_PURCHASE_FIELDS = "UPDATE_PURCHASE_FIELDS"
    SUBMIT_WAREHOUSE = "SUBMIT_WAREHOUSE"
    UPDATE_WAREHOUSE_FIELDS = "UPDATE_WAREHOUSE_FIELDS"
    COMPLETE = "COMPLETE"


class ReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"


class BuildingManagerAction(StrEnum):
    LIST_PENDING = "building_manager.list_pending"
    OPEN_REQUIREMENT = "building_manager.open_requirement"
    SAVE_REVIEW_FIELDS = "building_manager.save_review_fields"
    PREPARE_REJECT = "building_manager.prepare_reject"
    CONFIRM_REJECT = "building_manager.confirm_reject"
    PREPARE_SUBMIT_PURCHASER = "building_manager.prepare_submit_purchaser"
    CONFIRM_SUBMIT_PURCHASER = "building_manager.confirm_submit_purchaser"
    REFRESH = "building_manager.refresh"


class PurchaserAction(StrEnum):
    LIST_PENDING = "purchaser.list_pending"
    OPEN_REQUIREMENT = "purchaser.open_requirement"
    START_PURCHASE = "purchaser.start_purchase"
    SEARCH_SUPPLIER = "purchaser.search_supplier"
    SELECT_SUPPLIER = "purchaser.select_supplier"
    PREPARE_CREATE_SUPPLIER = "purchaser.prepare_create_supplier"
    CREATE_SUPPLIER = "purchaser.create_supplier"
    SAVE_PURCHASE_FIELDS = "purchaser.save_purchase_fields"
    PREPARE_SUBMIT_WAREHOUSE = "purchaser.prepare_submit_warehouse"
    CONFIRM_SUBMIT_WAREHOUSE = "purchaser.confirm_submit_warehouse"
    REFRESH = "purchaser.refresh"


class WarehouseAction(StrEnum):
    LIST_PENDING = "warehouse.list_pending"
    OPEN_REQUIREMENT = "warehouse.open_requirement"
    SAVE_FIELDS = "warehouse.save_fields"
    PREPARE_COMPLETE = "warehouse.prepare_complete"
    CONFIRM_COMPLETE = "warehouse.confirm_complete"
    REFRESH = "warehouse.refresh"
