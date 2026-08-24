from procurement_platform.application.assistant.capabilities.policy import CapabilityPolicy
from procurement_platform.application.assistant.role_skills import WorkflowPhaseDefinition
from procurement_platform.application.assistant.workflow_execution import TurnExecutionBudget


class WorkflowTurnCoordinator:
    def __init__(self, policy: CapabilityPolicy, *, max_read_phases: int = 3) -> None:
        self._policy = policy
        self._max_read_phases = max_read_phases

    def budget(self) -> TurnExecutionBudget:
        return TurnExecutionBudget(max_phase_steps=self._max_read_phases)

    def is_readonly(self, phase: WorkflowPhaseDefinition) -> bool:
        return bool(phase.capabilities) and all(
            self._policy.side_effect_for(name) == "READ" for name in phase.capabilities
        )

    def can_retry(self, phase: WorkflowPhaseDefinition, attempts: int) -> bool:
        return self.is_readonly(phase) and attempts < phase.retry

    def can_continue(self, phase: WorkflowPhaseDefinition, budget: TurnExecutionBudget) -> bool:
        return (
            phase.input_parser is None
            and (
                self.is_readonly(phase)
                or (
                    bool(phase.capabilities)
                    and not budget.mutation_seen
                    and all(
                        self._policy.side_effect_for(name) == "MUTATE"
                        for name in phase.capabilities
                    )
                )
            )
            and budget.phase_steps < budget.max_phase_steps
        )
