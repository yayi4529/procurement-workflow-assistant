from .cases import PURCHASER_CASES


def test_purchaser_language_case_coverage() -> None:
    assert 15 <= len(PURCHASER_CASES) <= 25
    assert any(len(case.expected_tools) >= 3 for case in PURCHASER_CASES)
    assert any(
        case.fixture == "ambiguous_prices" and case.clarification_expected
        for case in PURCHASER_CASES
    )
