from .cases import BUILDING_MANAGER_CASES


def test_building_manager_language_case_coverage() -> None:
    assert 15 <= len(BUILDING_MANAGER_CASES) <= 25
    names = {call.name for case in BUILDING_MANAGER_CASES for call in case.expected_tools}
    assert {
        "recommend_suppliers_for_requirement",
        "query_supplier_profile",
        "update_review_draft",
    } <= names
    assert any(
        len(call.arguments_subset) >= 3
        for case in BUILDING_MANAGER_CASES
        for call in case.expected_tools
    )
