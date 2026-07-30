import json
from collections.abc import Awaitable

from procurement_platform.adapters.feishu.error_mapping import map_feishu_delivery_error
from procurement_platform.adapters.feishu.interaction_renderer import (
    FeishuInteractionRenderer,
)
from procurement_platform.adapters.feishu.sdk_client import FeishuSdkResult, FeishuSdkTransport
from procurement_platform.domain.channel import (
    ChannelDeliveryResult,
    ChannelRecipient,
    ChannelType,
)
from procurement_platform.domain.interaction import InteractionView


class FeishuChannelClient:
    def __init__(self, transport: FeishuSdkTransport, renderer: FeishuInteractionRenderer) -> None:
        self._transport = transport
        self._renderer = renderer

    async def reply_text(self, *, reply_to_message_id: str, text: str) -> ChannelDeliveryResult:
        return await self._invoke(
            self._transport.reply(
                message_id=reply_to_message_id,
                message_type="text",
                content=json.dumps({"text": text}, ensure_ascii=False),
            )
        )

    async def reply_interaction(
        self, *, reply_to_message_id: str, view: InteractionView
    ) -> ChannelDeliveryResult:
        return await self._invoke(
            self._transport.reply(
                message_id=reply_to_message_id,
                message_type="interactive",
                content=json.dumps(self._renderer.render(view), ensure_ascii=False),
            )
        )

    async def update_interaction(
        self, *, message_id: str, view: InteractionView
    ) -> ChannelDeliveryResult:
        return await self._invoke(
            self._transport.update_card(message_id=message_id, card=self._renderer.render(view))
        )

    async def send_text(self, *, recipient: ChannelRecipient, text: str) -> ChannelDeliveryResult:
        self._validate_recipient(recipient)
        return await self._invoke(
            self._transport.send(
                receive_id_type="open_id",
                receive_id=recipient.platform_user_id,
                message_type="text",
                content=json.dumps({"text": text}, ensure_ascii=False),
            )
        )

    async def send_interaction(
        self, *, recipient: ChannelRecipient, view: InteractionView
    ) -> ChannelDeliveryResult:
        self._validate_recipient(recipient)
        return await self._invoke(
            self._transport.send(
                receive_id_type="open_id",
                receive_id=recipient.platform_user_id,
                message_type="interactive",
                content=json.dumps(self._renderer.render(view), ensure_ascii=False),
            )
        )

    @staticmethod
    def _validate_recipient(recipient: ChannelRecipient) -> None:
        if recipient.channel != ChannelType.FEISHU:
            raise ValueError("FeishuChannelClient only supports FEISHU")

    @staticmethod
    async def _invoke(awaitable: Awaitable[FeishuSdkResult]) -> ChannelDeliveryResult:
        try:
            result = await awaitable
        except Exception as exc:
            raise map_feishu_delivery_error(exc) from exc
        return ChannelDeliveryResult(
            external_message_id=result.message_id,
            delivered=True,
        )

    async def aclose(self) -> None:
        await self._transport.aclose()
