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
