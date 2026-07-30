from typing import cast

from procurement_platform.adapters.feishu.interaction_renderer import (
    FeishuInteractionRenderer,
)
from procurement_platform.domain.interaction import (
    ActionButton,
    InteractionView,
    KeyValueField,
    KeyValueSection,
    MarkdownBlock,
    PlainTextBlock,
)
from procurement_platform.domain.json_types import JsonObject


def test_renderer_produces_feishu_card_without_identity() -> None:
    card = FeishuInteractionRenderer().render(
        InteractionView(
            title="Title",
            subtitle="Subtitle",
            elements=(
                PlainTextBlock(text="Plain"),
                MarkdownBlock(markdown="**Markdown**"),
                KeyValueSection(fields=(KeyValueField(label="A", value="B"),)),
            ),
            actions=(
                ActionButton(
                    action_id="foundation.echo",
                    label="Echo",
                    value={"reference": "stable"},
                ),
            ),
        )
    )
    header = cast(JsonObject, card["header"])
    title = cast(JsonObject, header["title"])
    assert title["content"] == "Title"
    serialized = str(card)
    assert "foundation.echo" in serialized
    assert "operator_open_id" not in serialized


def test_renderer_wraps_inputs_and_submit_buttons_in_form() -> None:
    from procurement_platform.domain.interaction import SelectInput, SelectOption

    card = FeishuInteractionRenderer().render(
        InteractionView(
            title="Form",
            elements=(
                SelectInput(
                    name="building_id",
                    label="Building",
                    options=(SelectOption(label="One", value="1"),),
                    required=True,
                    default_value="1",
                ),
            ),
            actions=(ActionButton(action_id="applicant.create_draft", label="Create"),),
        )
    )
    elements = cast(list[JsonObject], card["elements"])
    form = elements[0]
    assert form["tag"] == "form"
    form_elements = cast(list[JsonObject], form["elements"])
    assert form_elements[0]["name"] == "building_id"
    assert form_elements[1]["action_type"] == "form_submit"
    assert form_elements[1]["name"] == "applicant_create_draft"
