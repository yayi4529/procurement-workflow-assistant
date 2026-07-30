from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.ports.channel import ChannelClient


class BaseMessageHandler:
    def __init__(self, channel_client: ChannelClient) -> None:
        self._channel_client = channel_client

    async def handle(self, event: TextMessageEvent) -> None:
        if event.external_message_id is None:
            return
        await self._channel_client.reply_text(
            reply_to_message_id=event.external_message_id,
            text="采购中心已收到您的消息。智能助手将在后续任务中接入。",
        )
