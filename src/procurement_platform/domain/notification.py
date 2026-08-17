from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.interaction import InteractionView
from procurement_platform.domain.json_types import JsonObject


class NotificationGatewayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    notification_id: int = Field(gt=0)
    dedup_key: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    platform_type: PlatformType
    receiver_platform_user_id: str = Field(min_length=1)
    payload: JsonObject


class TextNotification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["TEXT"] = "TEXT"
    text: str = Field(min_length=1)


class InteractionNotification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["INTERACTION"] = "INTERACTION"
    view: InteractionView


NotificationContent = Annotated[
    TextNotification | InteractionNotification, Field(discriminator="kind")
]
