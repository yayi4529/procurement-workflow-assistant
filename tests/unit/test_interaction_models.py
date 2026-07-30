from datetime import date

import pytest
from pydantic import ValidationError

from procurement_platform.domain.interaction import (
    ActionButton,
    DateInput,
    InteractionView,
    PlainTextBlock,
    SelectInput,
    SelectOption,
    TextInput,
)


def test_interaction_models_are_strict_and_serializable() -> None:
    view = InteractionView(
        title="test",
        elements=(
            PlainTextBlock(text="hello"),
            TextInput(name="amount", label="Amount", default_value="12.50"),
            SelectInput(
                name="choice",
                label="Choice",
                options=(SelectOption(label="One", value="1"),),
            ),
            DateInput(name="date", label="Date", default_value=date(2026, 7, 30)),
        ),
        actions=(ActionButton(action_id="foundation.echo", label="Echo"),),
    )
    assert view.model_dump(mode="json")["elements"][1]["default_value"] == "12.50"

    with pytest.raises(ValidationError):
        InteractionView(title="x", elements=(), unknown=True)  # type: ignore[call-arg]


def test_action_rejects_identity_fields() -> None:
    with pytest.raises(ValidationError, match="identity"):
        ActionButton(action_id="x", label="x", value={"roles": ["ADMIN"]})
