from typing import Protocol

from procurement_platform.domain.channel import (
    ChannelDeliveryResult,
    ChannelRecipient,
    StreamingCardHandle,
)
from procurement_platform.domain.interaction import InteractionView


class ChannelClient(Protocol):
    async def begin_streaming_reply(
        self, *, reply_to_message_id: str
    ) -> StreamingCardHandle | None: ...
    async def update_streaming_reply(
        self, *, handle: StreamingCardHandle, text: str, finish: bool = False
    ) -> StreamingCardHandle: ...
    async def reply_text(self, *, reply_to_message_id: str, text: str) -> ChannelDeliveryResult: ...
    async def reply_interaction(
        self, *, reply_to_message_id: str, view: InteractionView
    ) -> ChannelDeliveryResult: ...
    async def update_interaction(
        self, *, message_id: str, view: InteractionView
    ) -> ChannelDeliveryResult: ...
    async def send_text(
        self, *, recipient: ChannelRecipient, text: str
    ) -> ChannelDeliveryResult: ...
    async def send_interaction(
        self, *, recipient: ChannelRecipient, view: InteractionView
    ) -> ChannelDeliveryResult: ...

    async def aclose(self) -> None: ...
