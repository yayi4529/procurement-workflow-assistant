from decimal import Decimal, InvalidOperation


def quantity_text(value: str | None, *, empty: str = "-") -> str:
    if value is None:
        return empty
    try:
        number = Decimal(value)
    except InvalidOperation:
        return value
    if number == number.to_integral_value():
        return format(number.quantize(Decimal("1")), "f")
    return format(number.normalize(), "f")
