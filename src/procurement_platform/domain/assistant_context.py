"""Task-oriented assistant context models independent from LLM providers."""

from decimal import Decimal, InvalidOperation
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from procurement_platform.domain.assistant_session import JsonValue
from procurement_platform.domain.enums import (
    PurchaseItemKind,
    RequestType,
    RequirementStatus,
    RoleCode,
)


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


class AgentDraftItem(ContextModel):
    draft_item_id: str = Field(pattern=r"^draft-item-[1-9][0-9]*$")
    request_item_id: int | None = None
    item_kind: PurchaseItemKind
    item_name: str = Field(min_length=1, max_length=200)
    quantity: str
    unit: str = Field(min_length=1, max_length=30)
    requires_warehouse: bool | None = None
    equipment_category_id: int | None = None
    equipment_model_id: int | None = None
    brand: str | None = None
    model: str | None = None
    item_reason: str | None = None
    remark: str | None = None

    @model_validator(mode="after")
    def quantity_is_positive(self) -> "AgentDraftItem":
        try:
            if Decimal(self.quantity) <= 0:
                raise ValueError("quantity must be positive")
        except InvalidOperation as exc:
            raise ValueError("quantity must be a decimal string") from exc
        return self


class MultiItemRequestDraft(ContextModel):
    request_type: RequestType | None = None
    source_asset_ref: str | None = None
    application_reason: str | None = None
    items: tuple[AgentDraftItem, ...] = ()


class AgentTaskState(ContextModel):
    schema_version: int = 2
    active_goal: str | None = None
    known: dict[str, JsonValue] = Field(default_factory=dict)
    unresolved: tuple[str, ...] = ()
    pending_choice: PendingChoice | None = None
    pending_confirmation: bool = False
    last_observation_capability: str | None = None
    request_draft: MultiItemRequestDraft | None = None


ReferencePayload: TypeAlias = dict[str, JsonValue]


class StoredReference(ContextModel):
    schema_version: int = 2
    reference_id: str
    entity_type: str
    source_capability: str
    label: str
    payload: ReferencePayload = Field(default_factory=dict)
