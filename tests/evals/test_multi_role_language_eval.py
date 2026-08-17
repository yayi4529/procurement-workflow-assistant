import pytest

from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.assistant.role_intent import LlmRoleIntentResolver
from procurement_platform.domain.assistant import AssistantTurn
from procurement_platform.domain.enums import RoleCode

from .cases import MULTI_ROLE_CASES
from .helpers import evaluate, summarize


@pytest.mark.asyncio
async def test_multi_role_case_coverage_and_safety_metrics() -> None:
    assert len(MULTI_ROLE_CASES) == 4
    assert {case.case_id for case in MULTI_ROLE_CASES} == {
        "multi_role_applicant_to_manager_001",
        "multi_role_manager_to_applicant_001",
        "multi_role_keep_current_001",
        "multi_role_ambiguous_001",
    }
    scripted = {
        "multi_role_applicant_to_manager_001": '{"selection_index":2,"confidence":"HIGH"}',
        "multi_role_manager_to_applicant_001": '{"selection_index":1,"confidence":"HIGH"}',
        "multi_role_keep_current_001": '{"selection_index":2,"confidence":"LOW"}',
        "multi_role_ambiguous_001": '{"selection_index":1,"confidence":"LOW"}',
    }
    results = []
    for case in MULTI_ROLE_CASES:
        llm = FakeLlmClient(turns=(AssistantTurn(content=scripted[case.case_id]),))
        resolution = await LlmRoleIntentResolver(llm).resolve(
            user_text=case.user_messages[0],
            allowed_roles=case.allowed_roles,
            focused_role=case.initial_role,
        )
        selected_role = resolution.role if resolution.confidence == "HIGH" else case.initial_role
        results.append(
            evaluate(
                case,
                (),
                (),
                {},
                selected_role=selected_role,
                llm_turn_count=len(llm.calls),
            )
        )
    metrics = summarize(results)
    assert metrics.role_selection_accuracy == 1
    assert metrics.unnecessary_role_switch_count == 0
    assert metrics.unauthorized_role_selection_count == 0
    assert metrics.average_tool_calls == 0
    assert metrics.average_llm_turns == 1
    assert metrics.unsafe_action_rate == 0


def test_unauthorized_role_selection_is_counted() -> None:
    case = MULTI_ROLE_CASES[0]
    result = evaluate(case, (), (), {}, selected_role=RoleCode.PURCHASER)
    metrics = summarize((result,))

    assert not result.passed
    assert metrics.unauthorized_role_selection_count == 1
