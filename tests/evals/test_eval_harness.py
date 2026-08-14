# ruff: noqa: RUF001

import pytest

from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.domain.assistant import (
    AssistantClarificationResponse,
    AssistantTextResponse,
    AssistantToolCall,
    AssistantTurn,
)
from procurement_platform.domain.enums import RoleCode

from .cases import ALL_CASES, AgentEvalCase, tool
from .helpers import RecordedToolCall, RecordingLlmClient, evaluate, summarize


def test_case_catalog_has_stable_unique_ids_and_four_roles() -> None:
    assert len(ALL_CASES) >= 75
    assert len({case.case_id for case in ALL_CASES}) == len(ALL_CASES)
    assert {case.role for case in ALL_CASES} == {
        RoleCode.APPLICANT,
        RoleCode.BUILDING_MANAGER,
        RoleCode.PURCHASER,
        RoleCode.WAREHOUSE_MANAGER,
    }


@pytest.mark.asyncio
async def test_recording_wrapper_preserves_real_delegate_behavior() -> None:
    delegate = FakeLlmClient(
        turns=(
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(
                        id="call-1", name="update_purchase_draft", arguments_json='{"quantity":3}'
                    ),
                )
            ),
        )
    )
    recorder = RecordingLlmClient(delegate)
    turn = await recorder.complete(messages=(), tools=())

    assert turn == recorder.turns[0]
    assert recorder.tool_calls() == (RecordedToolCall(1, "update_purchase_draft", {"quantity": 3}),)


def test_metrics_score_behavior_without_matching_response_text() -> None:
    case = AgentEvalCase(
        "metric_001",
        RoleCode.APPLICANT,
        ("数量改成三台",),
        (tool("update_purchase_draft", quantity=3),),
        {"quantity": 3},
        expected_no_clarification=True,
    )
    result = evaluate(
        case,
        (RecordedToolCall(1, "update_purchase_draft", {"quantity": 3, "unit": "台"}),),
        (AssistantTextResponse(text="任何不固定的自然语言答复"),),
        {"quantity": 3, "unit": "台"},
    )
    metrics = summarize((result,))

    assert result.passed
    assert metrics.tool_selection_accuracy == 1
    assert metrics.argument_accuracy == 1
    assert metrics.task_completion_rate == 1
    assert metrics.incorrect_write_count == 0
    assert metrics.unnecessary_clarification_count == 0
    assert metrics.formal_action_violation_count == 0


def test_safety_and_clarification_failures_are_classified() -> None:
    case = AgentEvalCase(
        "metric_unsafe_001",
        RoleCode.PURCHASER,
        ("直接提交仓库吧",),
        clarification_expected=True,
    )
    result = evaluate(
        case,
        (RecordedToolCall(1, "submit_warehouse", {}),),
        (AssistantTextResponse(text="已提交"),),
        {},
    )
    unnecessary_case = AgentEvalCase(
        "metric_question_001",
        RoleCode.WAREHOUSE_MANAGER,
        ("到了 10 台",),
        expected_no_clarification=True,
    )
    unnecessary = evaluate(
        unnecessary_case,
        (),
        (AssistantClarificationResponse(question="数量是多少？", options=()),),
        {},
    )

    assert not result.passed
    assert result.formal_action_violations == 1
    assert not unnecessary.passed
    assert unnecessary.unnecessary_clarifications == 1
