from dataclasses import dataclass
from typing import Protocol

from procurement_platform.domain.json_types import JsonObject


@dataclass(frozen=True, slots=True)
class FeishuSdkResult:
    message_id: str | None


class FeishuSdkTransport(Protocol):
    async def create_streaming_card(self, *, content: str) -> str: ...
    async def update_streaming_content(
        self, *, card_id: str, element_id: str, content: str, sequence: int
    ) -> None: ...
    async def finish_streaming_card(self, *, card_id: str, sequence: int) -> None: ...
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
        self._app_id = app_id
        self._app_secret = app_secret

    async def _cardkit_request(self, method: str, path: str, payload: JsonObject) -> JsonObject:
        import httpx

        async with httpx.AsyncClient(base_url="https://open.feishu.cn", timeout=15) as client:
            token_response = await client.post(
                "/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self._app_id, "app_secret": self._app_secret},
            )
            token_response.raise_for_status()
            token = token_response.json().get("tenant_access_token")
            if not isinstance(token, str) or not token:
                raise RuntimeError("Feishu tenant token response is invalid")
            response = await client.request(
                method,
                path,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            raw_body = response.json()
            if not isinstance(raw_body, dict):
                raise RuntimeError("Feishu CardKit response is invalid")
            body: JsonObject = raw_body
            if body.get("code") != 0:
                raise RuntimeError(f"Feishu CardKit request failed with code {body.get('code')}")
            return body

    async def create_streaming_card(self, *, content: str) -> str:
        import json

        card = {
            "schema": "2.0",
            "header": {"title": {"tag": "plain_text", "content": "采购助手"}},
            "config": {
                "streaming_mode": True,
                "summary": {"content": "采购助手处理中"},
                "streaming_config": {"print_strategy": "fast"},
            },
            "body": {
                "elements": [
                    {"tag": "markdown", "content": content, "element_id": "agent_progress"}
                ]
            },
        }
        body = await self._cardkit_request(
            "POST",
            "/open-apis/cardkit/v1/cards",
            {"type": "card_json", "data": json.dumps(card, ensure_ascii=False)},
        )
        data = body.get("data")
        card_id = data.get("card_id") if isinstance(data, dict) else None
        if not isinstance(card_id, str):
            raise RuntimeError("Feishu CardKit create response is invalid")
        return card_id

    async def update_streaming_content(
        self, *, card_id: str, element_id: str, content: str, sequence: int
    ) -> None:
        from uuid import uuid4

        await self._cardkit_request(
            "PUT",
            f"/open-apis/cardkit/v1/cards/{card_id}/elements/{element_id}/content",
            {"content": content, "sequence": sequence, "uuid": str(uuid4())},
        )

    async def finish_streaming_card(self, *, card_id: str, sequence: int) -> None:
        import json
        from uuid import uuid4

        await self._cardkit_request(
            "PATCH",
            f"/open-apis/cardkit/v1/cards/{card_id}/settings",
            {
                "settings": json.dumps({"config": {"streaming_mode": False}}),
                "sequence": sequence,
                "uuid": str(uuid4()),
            },
        )

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
