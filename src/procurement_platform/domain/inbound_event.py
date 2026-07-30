from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from procurement_platform.domain.json_types import JsonObject


class InboundEventBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    external_tenant_id: str | None = None
    external_user_id: str = Field(min_length=1)
    external_message_id: str | None = None
    occurred_at: datetime | None = None


class TextMessageEvent(InboundEventBase):
    event_type: Literal["TEXT_MESSAGE"] = "TEXT_MESSAGE"
    text: str = Field(min_length=1)
    chat_id: str | None = None


class CardInteractionEvent(InboundEventBase):
    event_type: Literal["CARD_INTERACTION"] = "CARD_INTERACTION"
    message_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    action_value: JsonObject = Field(default_factory=dict)
    form_values: JsonObject = Field(default_factory=dict)


InboundEvent = TextMessageEvent | CardInteractionEvent
