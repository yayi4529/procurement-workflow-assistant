from procurement_platform.domain.interaction import (
    ActionButton,
    DateInput,
    Divider,
    InteractionView,
    KeyValueSection,
    MarkdownBlock,
    PlainTextBlock,
    SelectInput,
    TextInput,
)
from procurement_platform.domain.json_types import JsonObject, JsonValue


class FeishuInteractionRenderer:
    def render(self, view: InteractionView) -> JsonObject:
        elements: list[JsonValue] = []
        if view.subtitle:
            elements.append({"tag": "markdown", "content": view.subtitle})
        for element in view.elements:
            if isinstance(element, PlainTextBlock):
                elements.append(
                    {"tag": "div", "text": {"tag": "plain_text", "content": element.text}}
                )
            elif isinstance(element, MarkdownBlock):
                elements.append({"tag": "markdown", "content": element.markdown})
            elif isinstance(element, KeyValueSection):
                elements.append(
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**{field.label}**\n{field.value}",
                                },
                            }
                            for field in element.fields
                        ],
                    }
                )
            elif isinstance(element, Divider):
                elements.append({"tag": "hr"})
            elif isinstance(element, TextInput):
                item: JsonObject = {
                    "tag": "input",
                    "name": element.name,
                    "label": {"tag": "plain_text", "content": element.label},
                    "required": element.required,
                }
                if element.placeholder:
                    item["placeholder"] = {"tag": "plain_text", "content": element.placeholder}
                if element.default_value is not None:
                    item["default_value"] = element.default_value
                elements.append(item)
            elif isinstance(element, SelectInput):
                select: JsonObject = {
                    "tag": "select_static",
                    "name": element.name,
                    "label": {"tag": "plain_text", "content": element.label},
                    "required": element.required,
                    "options": [
                        {
                            "text": {"tag": "plain_text", "content": option.label},
                            "value": option.value,
                        }
                        for option in element.options
                    ],
                }
                if element.default_value is not None:
                    select["initial_option"] = element.default_value
                elements.append(select)
            elif isinstance(element, DateInput):
                date_picker: JsonObject = {
                    "tag": "date_picker",
                    "name": element.name,
                    "label": {"tag": "plain_text", "content": element.label},
                    "required": element.required,
                }
                if element.default_value is not None:
                    date_picker["initial_date"] = element.default_value.isoformat()
                elements.append(date_picker)
            else:
                raise TypeError(f"unsupported interaction element: {type(element).__name__}")
        if view.actions:
            elements.append(
                {
                    "tag": "action",
                    "actions": [self._render_button(button) for button in view.actions],
                }
            )
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": view.title},
            },
            "elements": elements,
        }

    @staticmethod
    def _render_button(button: ActionButton) -> JsonObject:
        return {
            "tag": "button",
            "text": {"tag": "plain_text", "content": button.label},
            "type": button.style,
            "value": {"action_id": button.action_id, **button.value},
        }
