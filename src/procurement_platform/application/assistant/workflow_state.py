import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from procurement_platform.domain.assistant_session import (
    AgentSessionState,
    AgentSessionStateUpdate,
    JsonValue,
)
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.errors import BackendApplicationError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.ports.backend_client import BackendClient

_WORKFLOW_STATE_KEY = "workflow_v1:state"


class WorkflowStatus(StrEnum):
    ACTIVE = "ACTIVE"
    AWAITING_USER = "AWAITING_USER"
    AWAITING_CARD = "AWAITING_CARD"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkflowRunState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 3
    role: RoleCode
    skill_name: str = Field(min_length=1, max_length=64)
    workflow_name: str = Field(min_length=1, max_length=64)
    phase: str = Field(min_length=1, max_length=64)
    status: WorkflowStatus = WorkflowStatus.ACTIVE
    route_confidence: str = "HIGH"
    collected_inputs: dict[str, JsonValue] = Field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    last_error_code: str | None = None
    clarification_count: int = 0
    phase_attempts: int = 0
    terminal_reason: str | None = None


class WorkflowStateService:
    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    @staticmethod
    def from_session(state: AgentSessionState | None) -> WorkflowRunState | None:
        if state is None:
            return None
        raw = state.collected_data.get(_WORKFLOW_STATE_KEY)
        if not isinstance(raw, str):
            return None
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return None
            version = payload.get("schema_version", 1)
            if version == 1:
                workflow_name = payload.get("workflow_name")
                old_phase = payload.get("phase")
                initial = {
                    "create-draft": "collect-items",
                    "fault-procurement": "identify-asset",
                    "product-recommendation": "identify-item",
                }.get(str(workflow_name))
                if old_phase == "execute" and initial is not None:
                    payload["phase"] = initial
            if version in {1, 2}:
                payload.setdefault("phase_attempts", 0)
                payload.setdefault("terminal_reason", None)
                payload["schema_version"] = 3
            return WorkflowRunState.model_validate(payload)
        except (ValidationError, ValueError, json.JSONDecodeError):
            return None

    async def save(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        session: AgentSessionState | None,
        workflow: WorkflowRunState | None,
    ) -> None:
        # Re-read immediately before the merge because capabilities may have updated
        # draft/task keys since the turn snapshot was built.
        try:
            session = await self._backend.get_agent_state(
                identity=identity, conversation_id=conversation_id
            )
        except BackendApplicationError:
            # The caller-provided snapshot remains a safe fallback for adapters that do
            # not create state until the first update.
            pass
        base = (
            AgentSessionStateUpdate.model_validate(
                session.model_dump(
                    exclude={"conversation_id", "expires_in_seconds", "restored_from_snapshot"}
                )
            )
            if session is not None
            else AgentSessionStateUpdate()
        )
        data = dict(base.collected_data)
        if workflow is None:
            data.pop(_WORKFLOW_STATE_KEY, None)
        else:
            data[_WORKFLOW_STATE_KEY] = workflow.model_dump_json()
        await self._backend.update_agent_state(
            identity=identity,
            conversation_id=conversation_id,
            state=base.model_copy(update={"collected_data": data}),
        )

    @staticmethod
    def encoded_key() -> str:
        return _WORKFLOW_STATE_KEY
