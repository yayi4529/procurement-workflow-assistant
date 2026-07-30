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
