from .cases import WAREHOUSE_CASES


def test_warehouse_language_case_coverage() -> None:
    assert 10 <= len(WAREHOUSE_CASES) <= 20
    assert any(case.clarification_expected for case in WAREHOUSE_CASES)
    assert any(case.expected_no_clarification for case in WAREHOUSE_CASES)
    assert any(
        len(call.arguments_subset) >= 2 for case in WAREHOUSE_CASES for call in case.expected_tools
    )
