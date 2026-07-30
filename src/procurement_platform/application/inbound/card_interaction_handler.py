from procurement_platform.domain.errors import UnsupportedCardActionError
from procurement_platform.domain.inbound_event import CardInteractionEvent
from procurement_platform.domain.interaction import InteractionView, PlainTextBlock
from procurement_platform.ports.channel import ChannelClient


class BaseCardInteractionHandler:
    def __init__(self, channel_client: ChannelClient) -> None:
        self._channel_client = channel_client

    async def handle(self, event: CardInteractionEvent) -> None:
        if event.action_id != "foundation.echo":
            raise UnsupportedCardActionError("不支持的卡片操作")
        await self._channel_client.update_interaction(
            message_id=event.message_id,
            view=InteractionView(
                title="基础链路验证",
                elements=(PlainTextBlock(text="卡片操作已收到。"),),
            ),
        )
