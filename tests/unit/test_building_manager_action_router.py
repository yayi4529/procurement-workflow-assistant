import pytest

from procurement_platform.application.building_manager.action_router import (
    _optional_positive_integer,
)
from procurement_platform.domain.json_types import JsonValue


def test_optional_positive_integer_accepts_numeric_supplier_id() -> None:
    assert _optional_positive_integer("8", "proposed_supplier_id") == 8
    assert _optional_positive_integer(8, "proposed_supplier_id") == 8
    assert _optional_positive_integer("", "proposed_supplier_id") is None


@pytest.mark.parametrize("value", ["\uff0c", "jjj", "0", "-1", True])
def test_optional_positive_integer_rejects_invalid_supplier_id(value: JsonValue) -> None:
    with pytest.raises(ValueError, match="must be a positive integer"):
        _optional_positive_integer(value, "proposed_supplier_id")
