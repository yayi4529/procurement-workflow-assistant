from datetime import datetime
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from procurement_platform.domain.enums import (
    AgentConversationStatus,
    AgentMessageSender,
    RoleCode,
)

JsonScalar: TypeAlias = str | int | bool | None
JsonValue: TypeAlias = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]


class SessionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RecommendationReference(SessionModel):
    reference_id: str
    kind: str
    label: str


class RecentVisibleMessage(SessionModel):
    sender_type: AgentMessageSender
    content: str
    created_at: datetime | None = None


class AgentConversation(SessionModel):
    conversation_id: int
    current_action: str = "ASSISTANT_CHAT"
    status: AgentConversationStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentMessage(SessionModel):
    message_id: int
    conversation_id: int
    external_message_id: str | None
    sender_type: AgentMessageSender
    content: str
    created_at: datetime


class AgentMessageWriteResult(SessionModel):
    message_id: int
    created_at: datetime
    duplicate: bool


class AgentMessagePage(SessionModel):
    items: tuple[AgentMessage, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    total: int = Field(ge=0)


class AgentSessionStateUpdate(SessionModel):
    purchase_request_id: int | None = None
    current_action: str | None = None
    collected_data: dict[str, JsonValue] = Field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()
    pending_field: str | None = None
    awaiting_confirmation: bool = False
    recent_messages: tuple[RecentVisibleMessage, ...] = ()
    last_recommendations: tuple[RecommendationReference, ...] = ()
    active_card_type: str | None = None
    focused_role: RoleCode | None = None
    focused_field: str | None = None


class AgentSessionState(AgentSessionStateUpdate):
    conversation_id: int
    expires_in_seconds: int = Field(gt=0)


class AgentStateSaveResult(SessionModel):
    conversation_id: int
    expires_in_seconds: int = Field(gt=0)
    updated_at: datetime


class AgentSessionSnapshot(SessionModel):
    snapshot_id: int
    conversation_id: int
    snapshot_reason: str
    created_at: datetime


class AgentConversationCompletion(SessionModel):
    conversation_id: int
    status: AgentConversationStatus
    redis_state_deleted: bool
    completed_at: datetime
