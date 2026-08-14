import json

import pytest

from procurement_platform.adapters.feishu.channel_client import FeishuChannelClient
from procurement_platform.adapters.feishu.interaction_renderer import (
    FeishuInteractionRenderer,
)
from procurement_platform.adapters.feishu.sdk_client import FeishuSdkResult
from procurement_platform.domain.channel import ChannelRecipient, ChannelType
from procurement_platform.domain.errors import FeishuTimeoutError
from procurement_platform.domain.interaction import InteractionView, PlainTextBlock
from procurement_platform.domain.json_types import JsonObject


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.error: Exception | None = None

    async def create_streaming_card(self, *, content: str) -> str:
        self.calls.append(("stream-create", content))
        return "card_1"

    async def update_streaming_content(
        self, *, card_id: str, element_id: str, content: str, sequence: int
    ) -> None:
        self.calls.append((f"stream-update:{card_id}:{element_id}:{sequence}", content))

    async def finish_streaming_card(self, *, card_id: str, sequence: int) -> None:
        self.calls.append((f"stream-finish:{card_id}:{sequence}", ""))

    async def _result(self) -> FeishuSdkResult:
        if self.error is not None:
            raise self.error
        return FeishuSdkResult("om_result")

    async def reply(self, *, message_id: str, message_type: str, content: str) -> FeishuSdkResult:
        self.calls.append(("reply", content))
        return await self._result()

    async def update_card(self, *, message_id: str, card: JsonObject) -> FeishuSdkResult:
        self.calls.append(("update", str(card)))
        return await self._result()

    async def send(
        self,
        *,
        receive_id_type: str,
        receive_id: str,
        message_type: str,
        content: str,
    ) -> FeishuSdkResult:
        assert receive_id_type == "open_id"
        self.calls.append((f"send:{receive_id}:{message_type}", content))
        return await self._result()

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_channel_replies_updates_and_sends_with_open_id() -> None:
    transport = FakeTransport()
    client = FeishuChannelClient(transport, FeishuInteractionRenderer())
    view = InteractionView(title="test", elements=(PlainTextBlock(text="content"),))
    await client.reply_text(reply_to_message_id="om", text="hello")
    await client.reply_interaction(reply_to_message_id="om", view=view)
    await client.update_interaction(message_id="om", view=view)
    recipient = ChannelRecipient(channel=ChannelType.FEISHU, platform_user_id="ou_user")
    result = await client.send_text(recipient=recipient, text="hello")
    await client.send_interaction(recipient=recipient, view=view)
    assert result.external_message_id == "om_result"
    assert json.loads(transport.calls[0][1]) == {"text": "hello"}
    assert transport.calls[3][0] == "send:ou_user:text"


@pytest.mark.asyncio
async def test_channel_maps_timeout() -> None:
    transport = FakeTransport()
    transport.error = TimeoutError()
    client = FeishuChannelClient(transport, FeishuInteractionRenderer())
    with pytest.raises(FeishuTimeoutError):
        await client.reply_text(reply_to_message_id="om", text="hello")


@pytest.mark.asyncio
async def test_channel_creates_updates_and_finishes_cardkit_stream() -> None:
    transport = FakeTransport()
    client = FeishuChannelClient(transport, FeishuInteractionRenderer())

    handle = await client.begin_streaming_reply(reply_to_message_id="om_source")
    assert handle is not None
    updated = await client.update_streaming_reply(handle=handle, text="最终答复", finish=True)

    assert updated.sequence == 2
    assert transport.calls[0] == ("stream-create", "正在理解你的需求…")
    assert transport.calls[2][0] == "stream-update:card_1:agent_progress:1"
    assert transport.calls[3][0] == "stream-finish:card_1:2"
