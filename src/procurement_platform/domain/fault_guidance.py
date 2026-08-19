from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from procurement_platform.domain.assets import AssetSummary
from procurement_platform.domain.assistant import AssistantMessage
from procurement_platform.domain.enums import FaultAction, PurchaseItemKind, ValidationStatus


@dataclass(frozen=True, slots=True)
class FaultKnowledge:
    knowledge_id: str
    title: str
    equipment_category: str
    knowledge_type: str
    aliases: list[str]
    risk_level: str
    version: int
    content: str


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResult:
    knowledge_id: str
    title: str
    equipment_category: str
    risk_level: str
    matched_aliases: list[str]
    content: str


@dataclass(slots=True)
class CandidateItem:
    item_kind: PurchaseItemKind | None
    item_name: str
    quantity: Decimal | None = None
    unit: str | None = None
    brand: str | None = None
    model: str | None = None
    item_evidence: str | None = None
    quantity_evidence: str | None = None


@dataclass(slots=True)
class FaultState:
    source_asset_ref: str | None = None
    issue_summary: str | None = None
    confirmed_facts: dict[str, Any] = field(default_factory=dict)
    candidate_items: list[CandidateItem] = field(default_factory=list)
    knowledge_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FaultContext:
    user_message: str
    source_asset: AssetSummary | None
    fault_state: FaultState
    knowledge_results: list[KnowledgeSearchResult]
    conversation_messages: list[AssistantMessage]


@dataclass(slots=True)
class FaultDecision:
    action: FaultAction
    reply: str
    issue_summary: str | None = None
    confirmed_facts_updates: dict[str, Any] = field(default_factory=dict)
    knowledge_refs_add: list[str] = field(default_factory=list)
    candidate_items: list[CandidateItem] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FaultDraftValidationResult:
    status: ValidationStatus
    missing_fields: list[str]
    errors: list[str]


@dataclass(frozen=True, slots=True)
class FaultDraftCandidate:
    source_asset_ref: str | None
    application_reason: str
    items: list[CandidateItem]


@dataclass(frozen=True, slots=True)
class ProcurementDraftResult:
    requirement_id: int
    requirement_no: str
    version: int


@dataclass(frozen=True, slots=True)
class FaultGuidanceResponse:
    reply: str
    action: FaultAction
    procurement_draft_ref: str | None = None
