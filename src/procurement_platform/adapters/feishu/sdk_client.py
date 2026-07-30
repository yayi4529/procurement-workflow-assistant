from dataclasses import dataclass
from typing import Protocol

from procurement_platform.domain.json_types import JsonObject


@dataclass(frozen=True, slots=True)
class FeishuSdkResult:
    message_id: str | None


class FeishuSdkTransport(Protocol):
    async def reply(
        self, *, message_id: str, message_type: str, content: str
    ) -> FeishuSdkResult: ...
    async def update_card(self, *, message_id: str, card: JsonObject) -> FeishuSdkResult: ...
    async def send(
        self,
        *,
        receive_id_type: str,
        receive_id: str,
        message_type: str,
        content: str,
    ) -> FeishuSdkResult: ...
    async def aclose(self) -> None: ...


class LarkOapiTransport:
    """Official SDK boundary.

    The SDK's generated request builders are synchronous; calls are isolated here so
    application and domain layers never depend on their response types.
    """

    def __init__(self, app_id: str, app_secret: str) -> None:
        import lark_oapi as lark

        self._client: object = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()

    async def reply(self, *, message_id: str, message_type: str, content: str) -> FeishuSdkResult:
        import asyncio

        import lark_oapi.api.im.v1 as im

        def call() -> object:
            body = (
                im.ReplyMessageRequestBody.builder().msg_type(message_type).content(content).build()
            )
            request = (
                im.ReplyMessageRequest.builder().message_id(message_id).request_body(body).build()
            )
            return self._client.im.v1.message.reply(request)  # type: ignore[attr-defined]

        return self._result(await asyncio.to_thread(call))

    async def update_card(self, *, message_id: str, card: JsonObject) -> FeishuSdkResult:
        import asyncio
        import json

        import lark_oapi.api.im.v1 as im

        def call() -> object:
            body = im.PatchMessageRequestBody.builder().content(json.dumps(card)).build()
            request = (
                im.PatchMessageRequest.builder().message_id(message_id).request_body(body).build()
            )
            return self._client.im.v1.message.patch(request)  # type: ignore[attr-defined]

        return self._result(await asyncio.to_thread(call))

    async def send(
        self,
        *,
        receive_id_type: str,
        receive_id: str,
        message_type: str,
        content: str,
    ) -> FeishuSdkResult:
        import asyncio

        import lark_oapi.api.im.v1 as im

        def call() -> object:
            body = (
                im.CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type(message_type)
                .content(content)
                .build()
            )
            request = (
                im.CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(body)
                .build()
            )
            return self._client.im.v1.message.create(request)  # type: ignore[attr-defined]

        return self._result(await asyncio.to_thread(call))

    @staticmethod
    def _result(response: object) -> FeishuSdkResult:
        success = getattr(response, "success", lambda: False)()
        if not success:
            code = getattr(response, "code", "unknown")
            raise RuntimeError(f"Feishu SDK request failed with code {code}")
        data = getattr(response, "data", None)
        message_id = getattr(getattr(data, "message", None), "message_id", None)
        return FeishuSdkResult(message_id=message_id)

    async def aclose(self) -> None:
        return None
