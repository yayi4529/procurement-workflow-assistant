from procurement_platform.domain.channel import ChannelDeliveryResult, ChannelRecipient
from procurement_platform.domain.interaction import InteractionView


class FakeFeishuClient:
    def __init__(
        self,
        result: ChannelDeliveryResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or ChannelDeliveryResult(
            external_message_id="fake-message-id", delivered=True
        )
        self.error = error
        self.reply_text_calls: list[tuple[str, str]] = []
        self.reply_interaction_calls: list[tuple[str, InteractionView]] = []
        self.update_interaction_calls: list[tuple[str, InteractionView]] = []
        self.send_text_calls: list[tuple[ChannelRecipient, str]] = []
        self.send_interaction_calls: list[tuple[ChannelRecipient, InteractionView]] = []

    async def _return(self) -> ChannelDeliveryResult:
        if self.error is not None:
            raise self.error
        return self.result

    async def reply_text(self, *, reply_to_message_id: str, text: str) -> ChannelDeliveryResult:
        self.reply_text_calls.append((reply_to_message_id, text))
        return await self._return()

    async def reply_interaction(
        self, *, reply_to_message_id: str, view: InteractionView
    ) -> ChannelDeliveryResult:
        self.reply_interaction_calls.append((reply_to_message_id, view))
        return await self._return()

    async def update_interaction(
        self, *, message_id: str, view: InteractionView
    ) -> ChannelDeliveryResult:
        self.update_interaction_calls.append((message_id, view))
        return await self._return()

    async def send_text(self, *, recipient: ChannelRecipient, text: str) -> ChannelDeliveryResult:
        self.send_text_calls.append((recipient, text))
        return await self._return()

    async def send_interaction(
        self, *, recipient: ChannelRecipient, view: InteractionView
    ) -> ChannelDeliveryResult:
        self.send_interaction_calls.append((recipient, view))
        return await self._return()

    async def aclose(self) -> None:
        return None
