from enum import StrEnum


class RoleCode(StrEnum):
    APPLICANT = "APPLICANT"
    BUILDING_MANAGER = "BUILDING_MANAGER"
    PURCHASER = "PURCHASER"
    WAREHOUSE_MANAGER = "WAREHOUSE_MANAGER"
    ADMIN = "ADMIN"


class PurchaseStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    REJECTED = "REJECTED"
    PENDING_PURCHASE = "PENDING_PURCHASE"
    PURCHASING = "PURCHASING"
    PENDING_WAREHOUSE = "PENDING_WAREHOUSE"
    COMPLETED = "COMPLETED"


class ReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"


class ReviewResult(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ConversationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class SenderType(StrEnum):
    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class AssetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    STANDBY = "STANDBY"
    MAINTENANCE = "MAINTENANCE"
    FAULT = "FAULT"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"
    RETIRED = "RETIRED"


class AssetCriticality(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AssetRelationType(StrEnum):
    CONNECTED_TO = "CONNECTED_TO"
    POWERED_BY = "POWERED_BY"
    FEEDS = "FEEDS"
    COOLED_BY = "COOLED_BY"
    MONITORED_BY = "MONITORED_BY"
    DEPENDS_ON = "DEPENDS_ON"
