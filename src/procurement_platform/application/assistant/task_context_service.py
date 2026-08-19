"""Compatibility-backed BusinessFacts, task-state and reference services.

The current backend exposes the legacy Agent state schema.  V2 state is therefore
encoded under reserved ``collected_data`` keys until a native backend contract is
available.  Business facts are always rebuilt from authoritative backend models.
"""

import json

from pydantic import ValidationError as PydanticValidationError

from procurement_platform.domain.assistant_context import (
    AgentTaskState,
    BusinessFacts,
    MultiItemRequestDraft,
    PendingChoice,
    StoredReference,
)
from procurement_platform.domain.assistant_session import (
    AgentSessionState,
    AgentSessionStateUpdate,
    JsonValue,
    RecommendationReference,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import RequirementDetail
from procurement_platform.domain.user import CurrentUser
from procurement_platform.ports.backend_client import BackendClient

_TASK_PREFIX = "task_v2:"
_REFERENCE_PREFIX = "reference_v2:"
_STATE_SCHEMA_VERSION = 2


class BusinessFactsBuilder:
    @staticmethod
    def build(user: CurrentUser, requirement: RequirementDetail | None) -> BusinessFacts:
        fields: dict[str, JsonValue] = {}
        if requirement is not None:
            fields = {
                key: value
                for key, value in requirement.applicant_fields.model_dump(mode="json").items()
                if value is None or isinstance(value, (str, int, bool))
            }
        return BusinessFacts(
            employee_id=user.employee_id,
            roles=tuple(item.role_code for item in user.roles),
            building_ids=tuple(item.building_id for item in user.buildings),
            requirement_id=requirement.requirement_id if requirement else None,
            requirement_no=requirement.requirement_no if requirement else None,
            requirement_status=requirement.status if requirement else None,
            requirement_version=requirement.version if requirement else None,
            authoritative_fields=fields,
        )


class ApplicationReasonComposer:
    """Compose a concise reason from explicit facts without inventing impact or cause."""

    @staticmethod
    def compose(*, building_name: str | None, device_name: str, symptom_text: str) -> str:
        building = building_name.strip() if building_name else ""
        device = device_name.strip()
        symptom = " ".join(symptom_text.split())
        prefix = f"{building}{device}" if building else device
        return f"{prefix}{symptom}, 需采购相关设备或部件以处理该情况。"


class AgentTaskStateService:
    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    @staticmethod
    def from_session(state: AgentSessionState | None) -> AgentTaskState:
        if state is None:
            return AgentTaskState()
        data = state.collected_data
        refs = data.get(f"{_TASK_PREFIX}pending_refs")
        pending = None
        if isinstance(refs, list) and all(isinstance(item, str) for item in refs):
            source = data.get(f"{_TASK_PREFIX}pending_source")
            pending = PendingChoice(
                candidate_refs=tuple(refs),
                source_capability=source if isinstance(source, str) else "unknown",
            )
        known = {
            key.removeprefix(f"{_TASK_PREFIX}known:"): value
            for key, value in data.items()
            if key.startswith(f"{_TASK_PREFIX}known:")
        }
        unresolved = data.get(f"{_TASK_PREFIX}unresolved")
        raw_request_draft = data.get(f"{_TASK_PREFIX}request_draft")
        request_draft = None
        if isinstance(raw_request_draft, str):
            try:
                parsed = json.loads(raw_request_draft)
                if isinstance(parsed, dict):
                    request_draft = MultiItemRequestDraft.model_validate(parsed)
            except (json.JSONDecodeError, PydanticValidationError):
                request_draft = None
        return AgentTaskState(
            active_goal=data.get(f"{_TASK_PREFIX}goal")
            if isinstance(data.get(f"{_TASK_PREFIX}goal"), str)
            else None,
            known=known,
            unresolved=tuple(unresolved)
            if isinstance(unresolved, list) and all(isinstance(item, str) for item in unresolved)
            else (),
            pending_choice=pending,
            pending_confirmation=state.awaiting_confirmation,
            last_observation_capability=(
                data.get(f"{_TASK_PREFIX}last_capability")
                if isinstance(data.get(f"{_TASK_PREFIX}last_capability"), str)
                else None
            ),
            request_draft=request_draft,
        )

    async def save(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        session: AgentSessionState | None,
        task: AgentTaskState,
        purchase_request_id: int | None = None,
    ) -> None:
        base = (
            AgentSessionStateUpdate.model_validate(
                session.model_dump(
                    exclude={"conversation_id", "expires_in_seconds", "restored_from_snapshot"}
                )
            )
            if session is not None
            else AgentSessionStateUpdate()
        )
        data = {
            key: value
            for key, value in base.collected_data.items()
            if not key.startswith(_TASK_PREFIX)
        }
        data[f"{_TASK_PREFIX}schema_version"] = _STATE_SCHEMA_VERSION
        if task.active_goal:
            data[f"{_TASK_PREFIX}goal"] = task.active_goal
        for key, value in task.known.items():
            data[f"{_TASK_PREFIX}known:{key}"] = value
        data[f"{_TASK_PREFIX}unresolved"] = list(task.unresolved)
        if task.pending_choice:
            data[f"{_TASK_PREFIX}pending_refs"] = list(task.pending_choice.candidate_refs)
            data[f"{_TASK_PREFIX}pending_source"] = task.pending_choice.source_capability
        if task.last_observation_capability:
            data[f"{_TASK_PREFIX}last_capability"] = task.last_observation_capability
        if task.request_draft is not None:
            data[f"{_TASK_PREFIX}request_draft"] = task.request_draft.model_dump_json()
        await self._backend.update_agent_state(
            identity=identity,
            conversation_id=conversation_id,
            state=base.model_copy(
                update={
                    "collected_data": data,
                    "awaiting_confirmation": task.pending_confirmation,
                    "purchase_request_id": (
                        purchase_request_id
                        if purchase_request_id is not None
                        else base.purchase_request_id
                    ),
                }
            ),
        )


class ReferenceStore:
    """Stable typed references persisted through the existing backend session port."""

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def save(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        state: AgentSessionState | None,
        references: tuple[StoredReference, ...],
    ) -> None:
        base = (
            AgentSessionStateUpdate.model_validate(
                state.model_dump(
                    exclude={"conversation_id", "expires_in_seconds", "restored_from_snapshot"}
                )
            )
            if state is not None
            else AgentSessionStateUpdate()
        )
        data = dict(base.collected_data)
        data[f"{_REFERENCE_PREFIX}schema_version"] = _STATE_SCHEMA_VERSION
        for item in references:
            data[f"{_REFERENCE_PREFIX}{item.reference_id}:source"] = item.source_capability
            data[f"{_REFERENCE_PREFIX}{item.reference_id}:type"] = item.entity_type
            for key, value in item.payload.items():
                data[f"{_REFERENCE_PREFIX}{item.reference_id}:payload:{key}"] = value
        await self._backend.update_agent_state(
            identity=identity,
            conversation_id=conversation_id,
            state=base.model_copy(
                update={
                    "collected_data": data,
                    "last_recommendations": tuple(
                        RecommendationReference(
                            reference_id=item.reference_id,
                            kind=item.entity_type,
                            label=item.label,
                        )
                        for item in references
                    ),
                }
            ),
        )

    @staticmethod
    def resolve(state: AgentSessionState, reference_id: str) -> StoredReference:
        reference = next(
            (item for item in state.last_recommendations if item.reference_id == reference_id),
            None,
        )
        if reference is None:
            raise ValueError("候选引用不存在或已过期")
        prefix = f"{_REFERENCE_PREFIX}{reference_id}:payload:"
        payload: dict[str, JsonValue] = {
            key.removeprefix(prefix): value
            for key, value in state.collected_data.items()
            if key.startswith(prefix)
        }
        source = state.collected_data.get(f"{_REFERENCE_PREFIX}{reference_id}:source")
        return StoredReference(
            reference_id=reference.reference_id,
            entity_type=reference.kind,
            source_capability=source if isinstance(source, str) else "legacy",
            label=reference.label,
            payload=payload,
        )
