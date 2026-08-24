from dataclasses import dataclass, field

from procurement_platform.domain.assistant import AssistantResponse


@dataclass(frozen=True, slots=True)
class CapabilityExecutionRecord:
    name: str
    status: str
    side_effect: str


@dataclass(slots=True)
class TurnExecutionBudget:
    max_phase_steps: int = 3
    phase_steps: int = 0
    tool_call_count: int = 0
    mutation_seen: bool = False

    def begin_phase(self) -> bool:
        if self.phase_steps >= self.max_phase_steps:
            return False
        self.phase_steps += 1
        return True


@dataclass(slots=True)
class WorkflowExecutionTrace:
    successful_capabilities: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    last_error_code: str | None = None
    terminal_reason: str | None = None
    capability_results: list[CapabilityExecutionRecord] = field(default_factory=list)
    tool_call_count: int = 0
    mutation_seen: bool = False
    phase_steps: int = 0


@dataclass(frozen=True, slots=True)
class WorkflowExecutionOutcome:
    response: AssistantResponse
    successful_capabilities: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    last_error_code: str | None = None
    terminal_reason: str | None = None
    capability_results: tuple[CapabilityExecutionRecord, ...] = ()
    tool_call_count: int = 0
    mutation_seen: bool = False
    phase_steps: int = 0
