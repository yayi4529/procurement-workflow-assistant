from procurement_platform.application.card_values import quantity_text


def test_quantity_text_removes_decimal_suffix_for_integer_values() -> None:
    assert quantity_text("5.000") == "5"
    assert quantity_text("0.000") == "0"
    assert quantity_text(None) == "-"


def test_quantity_text_preserves_real_fractional_values() -> None:
    assert quantity_text("5.500") == "5.5"
