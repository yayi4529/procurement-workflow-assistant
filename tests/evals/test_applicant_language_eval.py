from .cases import APPLICANT_CASES


def test_applicant_language_case_coverage() -> None:
    assert 15 <= len(APPLICANT_CASES) <= 25
    assert any(len(case.user_messages) > 1 for case in APPLICANT_CASES)
    assert any(case.clarification_expected for case in APPLICANT_CASES)
    assert any(
        "selection_index" in call.arguments_subset
        for case in APPLICANT_CASES
        for call in case.expected_tools
    )
