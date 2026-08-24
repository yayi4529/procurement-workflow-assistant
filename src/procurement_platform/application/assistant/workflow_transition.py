from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from procurement_platform.application.assistant.role_skills import RoleWorkflow
from procurement_platform.application.assistant.workflow_state import (
    WorkflowRunState,
    WorkflowStatus,
)
from procurement_platform.domain.assistant_session import JsonValue


class WorkflowTransitionEvent(StrEnum):
    INPUT_MATCH = "INPUT_MATCH"
    INPUT_AMBIGUOUS = "INPUT_AMBIGUOUS"
    CAPABILITY_SUCCESS = "CAPABILITY_SUCCESS"
    CAPABILITY_FAILURE = "CAPABILITY_FAILURE"
    CARD_COMPLETED = "CARD_COMPLETED"
    NEW_GOAL = "NEW_GOAL"
    RESET = "RESET"


class WorkflowTransitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: WorkflowRunState | None
    previous_phase: str
    next_phase: str | None
    terminal_reason: str | None = None


class WorkflowTransitionService:
    def switch_workflow(
        self,
        *,
        state: WorkflowRunState,
        target_workflow: RoleWorkflow,
        target_phase: str,
        collected_inputs: dict[str, JsonValue],
        status: WorkflowStatus = WorkflowStatus.ACTIVE,
    ) -> WorkflowTransitionResult:
        if target_workflow.phase(target_phase) is None:
            raise ValueError(f"unknown target phase: {target_workflow.name}/{target_phase}")
        merged = dict(state.collected_inputs)
        merged.update(collected_inputs)
        updated = state.model_copy(
            update={
                "workflow_name": target_workflow.name,
                "phase": target_phase,
                "status": status,
                "collected_inputs": merged,
                "last_error_code": None,
                "clarification_count": 0,
                "phase_attempts": 0,
                "terminal_reason": None,
            }
        )
        return WorkflowTransitionResult(
            state=updated,
            previous_phase=state.phase,
            next_phase=target_phase,
        )

    def transition(
        self,
        *,
        state: WorkflowRunState,
        workflow: RoleWorkflow,
        event: WorkflowTransitionEvent,
        collected_inputs: dict[str, JsonValue] | None = None,
        evidence_refs: tuple[str, ...] = (),
        error_code: str | None = None,
        terminal_reason: str | None = None,
    ) -> WorkflowTransitionResult:
        phase = workflow.phase(state.phase)
        if phase is None:
            failed = state.model_copy(
                update={"status": WorkflowStatus.FAILED, "terminal_reason": "UNKNOWN_PHASE"}
            )
            return WorkflowTransitionResult(
                state=failed,
                previous_phase=state.phase,
                next_phase=None,
                terminal_reason="UNKNOWN_PHASE",
            )
        if event in {WorkflowTransitionEvent.NEW_GOAL, WorkflowTransitionEvent.RESET}:
            return WorkflowTransitionResult(
                state=None,
                previous_phase=state.phase,
                next_phase=None,
                terminal_reason=event.value,
            )
        merged = dict(state.collected_inputs)
        merged.update(collected_inputs or {})
        refs = tuple(dict.fromkeys((*state.evidence_refs, *evidence_refs)))[-50:]
        if event is WorkflowTransitionEvent.INPUT_AMBIGUOUS:
            updated = state.model_copy(
                update={
                    "status": WorkflowStatus.AWAITING_USER,
                    "clarification_count": state.clarification_count + 1,
                    "collected_inputs": merged,
                    "last_error_code": error_code,
                }
            )
            return WorkflowTransitionResult(
                state=updated, previous_phase=state.phase, next_phase=state.phase
            )
        if event is WorkflowTransitionEvent.CARD_COMPLETED:
            updated = state.model_copy(
                update={
                    "status": WorkflowStatus.COMPLETED,
                    "terminal_reason": terminal_reason or "FORMAL_CARD_COMPLETED",
                }
            )
            return WorkflowTransitionResult(
                state=updated,
                previous_phase=state.phase,
                next_phase=None,
                terminal_reason=updated.terminal_reason,
            )
        success = event in {
            WorkflowTransitionEvent.INPUT_MATCH,
            WorkflowTransitionEvent.CAPABILITY_SUCCESS,
        }
        target = phase.on_success if success else phase.on_failure
        if target in {"COMPLETED", "FAILED"}:
            updated = state.model_copy(
                update={
                    "status": WorkflowStatus(target),
                    "collected_inputs": merged,
                    "evidence_refs": refs,
                    "last_error_code": error_code,
                    "terminal_reason": terminal_reason or event.value,
                    "phase_attempts": 0,
                }
            )
            return WorkflowTransitionResult(
                state=updated,
                previous_phase=state.phase,
                next_phase=None,
                terminal_reason=updated.terminal_reason,
            )
        target_phase = workflow.phase(target)
        if target_phase is None:
            raise ValueError(f"unknown target phase: {target}")
        status = (
            WorkflowStatus(target_phase.terminal_status)
            if target_phase.terminal_status is not None
            else WorkflowStatus.ACTIVE
        )
        updated = state.model_copy(
            update={
                "phase": target,
                "status": status,
                "collected_inputs": merged,
                "evidence_refs": refs,
                "last_error_code": error_code,
                "terminal_reason": terminal_reason,
                "phase_attempts": 0,
                "clarification_count": 0,
            }
        )
        return WorkflowTransitionResult(
            state=updated, previous_phase=state.phase, next_phase=target
        )
