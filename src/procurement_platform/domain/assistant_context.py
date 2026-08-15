"""Task-oriented assistant context models independent from LLM providers."""

from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from procurement_platform.domain.assistant_session import JsonValue
from procurement_platform.domain.enums import RequirementStatus, RoleCode


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BusinessFacts(ContextModel):
    employee_id: int
    roles: tuple[RoleCode, ...]
    building_ids: tuple[int, ...]
    requirement_id: int | None = None
    requirement_no: str | None = None
    requirement_status: RequirementStatus | None = None
    requirement_version: int | None = None
    authoritative_fields: dict[str, JsonValue] = Field(default_factory=dict)


class PendingChoice(ContextModel):
    candidate_refs: tuple[str, ...]
    source_capability: str
    prompt_hint: str | None = None


class AgentTaskState(ContextModel):
    schema_version: int = 2
    active_goal: str | None = None
    known: dict[str, JsonValue] = Field(default_factory=dict)
    unresolved: tuple[str, ...] = ()
    pending_choice: PendingChoice | None = None
    pending_confirmation: bool = False
    last_observation_capability: str | None = None


ReferencePayload: TypeAlias = dict[str, JsonValue]


class StoredReference(ContextModel):
    schema_version: int = 2
    reference_id: str
    entity_type: str
    source_capability: str
    label: str
    payload: ReferencePayload = Field(default_factory=dict)
