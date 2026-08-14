from procurement_platform.domain.enums import RoleCode

from .cases import MULTI_ROLE_CASES
from .helpers import evaluate, summarize


def test_multi_role_case_coverage_and_safety_metrics() -> None:
    assert len(MULTI_ROLE_CASES) == 4
    assert {case.case_id for case in MULTI_ROLE_CASES} == {
        "multi_role_applicant_to_manager_001",
        "multi_role_manager_to_applicant_001",
        "multi_role_keep_current_001",
        "multi_role_ambiguous_001",
    }
    results = tuple(
        evaluate(case, (), (), {}, selected_role=case.expected_role)
        for case in MULTI_ROLE_CASES
        if not case.expected_tools
    )
    metrics = summarize(results)
    assert metrics.role_selection_accuracy == 1
    assert metrics.unnecessary_role_switch_count == 0
    assert metrics.unauthorized_role_selection_count == 0


def test_unauthorized_role_selection_is_counted() -> None:
    case = MULTI_ROLE_CASES[0]
    result = evaluate(case, (), (), {}, selected_role=RoleCode.PURCHASER)
    metrics = summarize((result,))

    assert not result.passed
    assert metrics.unauthorized_role_selection_count == 1
