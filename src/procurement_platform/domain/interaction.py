from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from procurement_platform.domain.json_types import JsonObject


class _Element(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PlainTextBlock(_Element):
    kind: Literal["plain_text"] = "plain_text"
    text: str = Field(min_length=1)


class MarkdownBlock(_Element):
    kind: Literal["markdown"] = "markdown"
    markdown: str = Field(min_length=1)


class KeyValueField(_Element):
    label: str = Field(min_length=1)
    value: str


class KeyValueSection(_Element):
    kind: Literal["key_value"] = "key_value"
    fields: tuple[KeyValueField, ...] = Field(min_length=1)


class Divider(_Element):
    kind: Literal["divider"] = "divider"


class TextInput(_Element):
    kind: Literal["text_input"] = "text_input"
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    placeholder: str | None = None
    required: bool = False
    default_value: str | None = None


class SelectOption(_Element):
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class SelectInput(_Element):
    kind: Literal["select_input"] = "select_input"
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    options: tuple[SelectOption, ...] = Field(min_length=1)
    required: bool = False
    default_value: str | None = None


class DateInput(_Element):
    kind: Literal["date_input"] = "date_input"
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    required: bool = False
    default_value: date | None = None


_FORBIDDEN_ACTION_KEYS = frozenset(
    {"employee_id", "operator_id", "operator_open_id", "roles", "role", "status", "current_handler"}
)


class ActionButton(_Element):
    kind: Literal["action_button"] = "action_button"
    action_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: JsonObject = Field(default_factory=dict)
    style: Literal["default", "primary", "danger"] = "default"

    @field_validator("value")
    @classmethod
    def reject_identity_fields(cls, value: JsonObject) -> JsonObject:
        if _FORBIDDEN_ACTION_KEYS.intersection(value):
            raise ValueError("action value must not contain identity, role, or status fields")
        return value


InteractionElement = Annotated[
    PlainTextBlock
    | MarkdownBlock
    | KeyValueSection
    | Divider
    | TextInput
    | SelectInput
    | DateInput,
    Field(discriminator="kind"),
]


class InteractionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1)
    subtitle: str | None = None
    elements: tuple[InteractionElement, ...]
    actions: tuple[ActionButton, ...] = ()
