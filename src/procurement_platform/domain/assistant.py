"""Platform-neutral models used by the optional conversational assistant."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from procurement_platform.domain.interaction import InteractionView
from procurement_platform.domain.user import CurrentUser

AssistantRole = Literal["system", "user", "assistant", "tool"]
ToolResultStatus = Literal[
    "SUCCESS",
    "NOT_FOUND",
    "MULTIPLE_MATCHES",
    "NEED_MORE_INFORMATION",
    "PERMISSION_DENIED",
    "INVALID_STATUS",
    "CONCURRENT_MODIFICATION",
    "BACKEND_UNAVAILABLE",
    "INVALID_ARGUMENTS",
    "INTERNAL_ERROR",
]


class AssistantToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    arguments_json: str


class AssistantMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: AssistantRole
    content: str | None
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: tuple[AssistantToolCall, ...] = ()


class AssistantTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    content: str | None = None
    tool_calls: tuple[AssistantToolCall, ...] = ()


class AssistantToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    description: str
    parameters: dict[str, object]
    side_effect: str


class AssistantToolContext(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    platform_type: str
    platform_user_id: str
    conversation_id: int
    external_conversation_id: str
    external_message_id: str
    current_time: datetime
    timezone_name: str
    current_user: CurrentUser
    active_requirement_id: int | None = None


class AssistantToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ToolResultStatus
    user_message: str | None = None
    requirement_id: int | None = None
    requirement_version: int | None = None
    candidate_set_id: str | None = None
    exact_render_required: bool = False


class AssistantTextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    text: str


class AssistantInteractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    view: InteractionView


class AssistantOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    label: str
    value: str


class AssistantClarificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    question: str
    options: tuple[AssistantOption, ...]


AssistantResponse = (
    AssistantTextResponse | AssistantInteractionResponse | AssistantClarificationResponse
)
