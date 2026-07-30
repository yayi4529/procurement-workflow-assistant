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
