from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ChannelType(StrEnum):
    FEISHU = "FEISHU"


class MessageKind(StrEnum):
    TEXT = "TEXT"
    INTERACTION = "INTERACTION"


class ChannelRecipient(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    channel: ChannelType
    platform_user_id: str = Field(min_length=1)


class ChannelDeliveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_message_id: str | None = None
    delivered: bool
