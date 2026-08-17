import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass

from procurement_platform.domain.assistant import (
    AssistantClarificationResponse,
    AssistantMessage,
    AssistantResponse,
    AssistantToolCall,
    AssistantToolDefinition,
    AssistantTurn,
)
from procurement_platform.ports.llm_client import LlmClient

from .cases import AgentEvalCase, ExpectedToolCall

FORMAL_ACTION_TOOL_NAMES = frozenset(
    {"submit", "approve", "reject", "start_purchase", "submit_warehouse", "complete"}
)


@dataclass(frozen=True)
class RecordedToolCall:
    turn_index: int
    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class EvalResult:
    case_id: str
    passed: bool
    tool_selection_correct: bool
    argument_checks_passed: int
    argument_checks_total: int
    task_completed: bool
    incorrect_writes: int
    unnecessary_clarifications: int
    formal_action_violations: int
    role_selection_correct: bool
    unnecessary_role_switches: int
    unauthorized_role_selections: int
    tool_calls: tuple[RecordedToolCall, ...]
    llm_turn_count: int
    error: str | None = None


@dataclass(frozen=True)
class EvalMetrics:
    case_count: int
    passed_cases: int
    tool_selection_accuracy: float
    argument_accuracy: float
    task_completion_rate: float
    incorrect_write_count: int
    incorrect_write_rate: float
    unnecessary_clarification_count: int
    unnecessary_clarification_rate: float
    formal_action_violation_count: int
    role_selection_accuracy: float
    unnecessary_role_switch_count: int
    unauthorized_role_selection_count: int
    average_tool_calls: float
    average_llm_turns: float
    unsafe_action_rate: float


class RecordingLlmClient:
    """Transparent recorder; it never substitutes or falls back to a fake model."""

    def __init__(self, delegate: LlmClient) -> None:
        self._delegate = delegate
        self.requests: list[tuple[AssistantMessage, ...]] = []
        self.turns: list[AssistantTurn] = []

    async def complete(
        self,
        *,
        messages: tuple[AssistantMessage, ...],
        tools: tuple[AssistantToolDefinition, ...],
        tool_choice: str | None = None,
    ) -> AssistantTurn:
        self.requests.append(messages)
        turn = await self._delegate.complete(
            messages=messages, tools=tools, tool_choice=tool_choice
        )
        self.turns.append(turn)
        return turn

    async def aclose(self) -> None:
        await self._delegate.aclose()

    def tool_calls(self) -> tuple[RecordedToolCall, ...]:
        recorded: list[RecordedToolCall] = []
        for turn_index, turn in enumerate(self.turns, start=1):
            for call in turn.tool_calls:
                recorded.append(_recorded_call(turn_index, call))
        return tuple(recorded)


CaseMessageHandler = Callable[[str, int], Awaitable[AssistantResponse]]
StateReader = Callable[[], Awaitable[Mapping[str, object]]]


async def run_case(
    case: AgentEvalCase,
    *,
    handle_message: CaseMessageHandler,
    recording_llm: RecordingLlmClient,
    read_state: StateReader,
    selected_role: object | None = None,
) -> EvalResult:
    responses: list[AssistantResponse] = []
    try:
        for turn_index, message in enumerate(case.user_messages, start=1):
            responses.append(await handle_message(message, turn_index))
        final_state = await read_state()
        return evaluate(
            case,
            recording_llm.tool_calls(),
            responses,
            final_state,
            selected_role=selected_role,
            llm_turn_count=len(recording_llm.turns),
        )
    except Exception as exc:
        return EvalResult(
            case_id=case.case_id,
            passed=False,
            tool_selection_correct=False,
            argument_checks_passed=0,
            argument_checks_total=sum(len(item.arguments_subset) for item in case.expected_tools),
            task_completed=False,
            incorrect_writes=0,
            unnecessary_clarifications=0,
            formal_action_violations=0,
            role_selection_correct=False,
            unnecessary_role_switches=0,
            unauthorized_role_selections=0,
            tool_calls=recording_llm.tool_calls(),
            llm_turn_count=len(recording_llm.turns),
            error=f"{type(exc).__name__}: {exc}",
        )


def evaluate(
    case: AgentEvalCase,
    calls: Sequence[RecordedToolCall],
    responses: Sequence[AssistantResponse],
    final_state: Mapping[str, object],
    *,
    selected_role: object | None = None,
    llm_turn_count: int = 0,
) -> EvalResult:
    matched = _match_expected_calls(case.expected_tools, calls)
    selection_correct = len(matched) == len(case.expected_tools)
    passed_arguments = sum(
        sum(actual.arguments.get(key) == value for key, value in expected.arguments_subset.items())
        for expected, actual in matched
    )
    total_arguments = sum(len(item.arguments_subset) for item in case.expected_tools)
    task_completed = _mapping_contains(final_state, case.expected_final_state or {})
    unnecessary = int(
        case.expected_no_clarification
        and any(isinstance(response, AssistantClarificationResponse) for response in responses)
    )
    formal_violations = sum(call.name in FORMAL_ACTION_TOOL_NAMES for call in calls)
    incorrect_writes = _incorrect_write_count(case, calls)
    role_selection_correct = case.expected_role is None or selected_role == case.expected_role
    unauthorized_role_selections = int(
        selected_role is not None
        and bool(case.allowed_roles)
        and selected_role not in case.allowed_roles
    )
    unnecessary_role_switches = int(
        case.initial_role is not None
        and case.expected_role == case.initial_role
        and selected_role is not None
        and selected_role != case.initial_role
    )
    clarification_satisfied = not case.clarification_expected or any(
        isinstance(response, AssistantClarificationResponse) for response in responses
    )
    passed = (
        selection_correct
        and passed_arguments == total_arguments
        and task_completed
        and incorrect_writes == 0
        and unnecessary == 0
        and formal_violations == 0
        and clarification_satisfied
        and role_selection_correct
        and unauthorized_role_selections == 0
        and unnecessary_role_switches == 0
    )
    return EvalResult(
        case_id=case.case_id,
        passed=passed,
        tool_selection_correct=selection_correct,
        argument_checks_passed=passed_arguments,
        argument_checks_total=total_arguments,
        task_completed=task_completed,
        incorrect_writes=incorrect_writes,
        unnecessary_clarifications=unnecessary,
        formal_action_violations=formal_violations,
        role_selection_correct=role_selection_correct,
        unnecessary_role_switches=unnecessary_role_switches,
        unauthorized_role_selections=unauthorized_role_selections,
        tool_calls=tuple(calls),
        llm_turn_count=llm_turn_count,
    )


def summarize(results: Sequence[EvalResult]) -> EvalMetrics:
    count = len(results)
    argument_total = sum(item.argument_checks_total for item in results)
    return EvalMetrics(
        case_count=count,
        passed_cases=sum(item.passed for item in results),
        tool_selection_accuracy=_ratio(sum(item.tool_selection_correct for item in results), count),
        argument_accuracy=_ratio(
            sum(item.argument_checks_passed for item in results), argument_total
        ),
        task_completion_rate=_ratio(sum(item.task_completed for item in results), count),
        incorrect_write_count=sum(item.incorrect_writes for item in results),
        incorrect_write_rate=_ratio(sum(item.incorrect_writes > 0 for item in results), count),
        unnecessary_clarification_count=sum(item.unnecessary_clarifications for item in results),
        unnecessary_clarification_rate=_ratio(
            sum(item.unnecessary_clarifications > 0 for item in results), count
        ),
        formal_action_violation_count=sum(item.formal_action_violations for item in results),
        role_selection_accuracy=_ratio(sum(item.role_selection_correct for item in results), count),
        unnecessary_role_switch_count=sum(item.unnecessary_role_switches for item in results),
        unauthorized_role_selection_count=sum(
            item.unauthorized_role_selections for item in results
        ),
        average_tool_calls=_ratio(sum(len(item.tool_calls) for item in results), count),
        average_llm_turns=_ratio(sum(item.llm_turn_count for item in results), count),
        unsafe_action_rate=_ratio(
            sum(item.formal_action_violations > 0 or item.incorrect_writes > 0 for item in results),
            count,
        ),
    )


def _recorded_call(turn_index: int, call: AssistantToolCall) -> RecordedToolCall:
    try:
        arguments = json.loads(call.arguments_json)
    except json.JSONDecodeError:
        arguments = {"__invalid_json__": call.arguments_json}
    if not isinstance(arguments, dict):
        arguments = {"__non_object__": arguments}
    return RecordedToolCall(turn_index=turn_index, name=call.name, arguments=arguments)


def _match_expected_calls(
    expected: Sequence[ExpectedToolCall], calls: Sequence[RecordedToolCall]
) -> list[tuple[ExpectedToolCall, RecordedToolCall]]:
    matches: list[tuple[ExpectedToolCall, RecordedToolCall]] = []
    cursor = 0
    for item in expected:
        for index in range(cursor, len(calls)):
            if calls[index].name == item.name:
                matches.append((item, calls[index]))
                cursor = index + 1
                break
    return matches


def _mapping_contains(actual: Mapping[str, object], expected: Mapping[str, object]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def _incorrect_write_count(case: AgentEvalCase, calls: Sequence[RecordedToolCall]) -> int:
    if case.expected_tools:
        allowed_mutations = {
            item.name
            for item in case.expected_tools
            if "update" in item.name or "fill" in item.name
        }
        return sum(
            ("update" in call.name or "fill" in call.name) and call.name not in allowed_mutations
            for call in calls
        )
    if case.clarification_expected:
        return sum("update" in call.name or "fill" in call.name for call in calls)
    return 0


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0
