import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from procurement_platform.domain.errors import (
    FeishuDecryptionError,
    FeishuProtocolError,
    FeishuVerificationError,
    UnsupportedInboundEventError,
)
from procurement_platform.domain.inbound_event import (
    CardInteractionEvent,
    InboundEvent,
    TextMessageEvent,
)
from procurement_platform.domain.json_types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class ChallengeResponse:
    challenge: str


class IgnoredEvent:
    pass


IGNORED_EVENT = IgnoredEvent()
WebhookParseResult = ChallengeResponse | InboundEvent | IgnoredEvent


class FeishuWebhookParser:
    def __init__(self, *, verification_token: str, encrypt_key: str | None = None) -> None:
        self._verification_token = verification_token
        self._encrypt_key = encrypt_key or None

    def parse(
        self,
        *,
        body: bytes,
        timestamp: str | None = None,
        nonce: str | None = None,
        signature: str | None = None,
    ) -> WebhookParseResult:
        if signature is not None:
            self._verify_signature(body, timestamp, nonce, signature)
        payload = self._load_json(body)
        encrypted = payload.get("encrypt")
        if isinstance(encrypted, str):
            payload = self._decrypt(encrypted)
        self._verify_token(payload)
        challenge = payload.get("challenge")
        if isinstance(challenge, str):
            return ChallengeResponse(challenge)
        return self._parse_event(payload)

    def _verify_signature(
        self, body: bytes, timestamp: str | None, nonce: str | None, signature: str
    ) -> None:
        if self._encrypt_key is None or timestamp is None or nonce is None:
            raise FeishuVerificationError("signature headers or encrypt key are missing")
        expected = hashlib.sha256(
            timestamp.encode() + nonce.encode() + self._encrypt_key.encode() + body
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise FeishuVerificationError("invalid Feishu signature")

    @staticmethod
    def _load_json(body: bytes) -> JsonObject:
        try:
            value = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FeishuProtocolError("invalid JSON payload") from exc
        if not isinstance(value, dict):
            raise FeishuProtocolError("payload must be an object")
        return cast(JsonObject, value)

    def _decrypt(self, encrypted: str) -> JsonObject:
        if self._encrypt_key is None:
            raise FeishuDecryptionError("encrypted event received without encrypt key")
        try:
            from lark_oapi.core.utils import AESCipher

            plaintext = AESCipher(self._encrypt_key).decrypt_str(encrypted)
            return self._load_json(plaintext.encode())
        except Exception as exc:
            raise FeishuDecryptionError("failed to decrypt Feishu event") from exc

    def _verify_token(self, payload: JsonObject) -> None:
        header = payload.get("header")
        header_token = header.get("token") if isinstance(header, dict) else None
        token = header_token if isinstance(header_token, str) else payload.get("token")
        if token != self._verification_token:
            raise FeishuVerificationError("invalid Feishu verification token")

    def _parse_event(self, payload: JsonObject) -> WebhookParseResult:
        header = payload.get("header")
        event = payload.get("event")
        if not isinstance(header, dict) or not isinstance(event, dict):
            return self._parse_legacy_card(payload)
        event_id = header.get("event_id")
        event_type = header.get("event_type")
        if not isinstance(event_id, str) or not event_id:
            raise FeishuProtocolError("event_id is required")
        if event_type == "im.message.receive_v1":
            return self._parse_message(header, event, event_id)
        if event_type in {"card.action.trigger", "card.action.trigger_v1"}:
            return self._parse_card(header, event, event_id)
        return IGNORED_EVENT

    def _parse_message(
        self, header: dict[str, JsonValue], event: dict[str, JsonValue], event_id: str
    ) -> WebhookParseResult:
        message = event.get("message")
        sender = event.get("sender")
        if not isinstance(message, dict) or not isinstance(sender, dict):
            raise FeishuProtocolError("message or sender is missing")
        if message.get("message_type") != "text":
            return IGNORED_EVENT
        if message.get("chat_type") != "p2p":
            return IGNORED_EVENT
        sender_id = sender.get("sender_id")
        open_id = sender_id.get("open_id") if isinstance(sender_id, dict) else None
        content = message.get("content")
        try:
            content_object = json.loads(content) if isinstance(content, str) else {}
        except json.JSONDecodeError as exc:
            raise FeishuProtocolError("invalid text message content") from exc
        text = content_object.get("text") if isinstance(content_object, dict) else None
        if not isinstance(open_id, str) or not open_id:
            raise FeishuProtocolError("sender open_id is required")
        if not isinstance(text, str) or not text.strip():
            raise FeishuProtocolError("text message must not be empty")
        return TextMessageEvent(
            event_id=event_id,
            external_tenant_id=self._string_or_none(header.get("tenant_key")),
            external_user_id=open_id,
            external_message_id=self._required_string(message, "message_id"),
            occurred_at=self._timestamp(header.get("create_time")),
            text=text.strip(),
            chat_id=self._string_or_none(message.get("chat_id")),
        )

    def _parse_card(
        self, header: dict[str, JsonValue], event: dict[str, JsonValue], event_id: str
    ) -> CardInteractionEvent:
        operator = event.get("operator")
        action = event.get("action")
        context = event.get("context")
        open_id = operator.get("open_id") if isinstance(operator, dict) else None
        if not isinstance(open_id, str):
            raise FeishuProtocolError("card operator open_id is required")
        if not isinstance(action, dict):
            raise FeishuProtocolError("card action is required")
        value = action.get("value")
        value_object: JsonObject = dict(value) if isinstance(value, dict) else {}
        action_id = value_object.pop("action_id", action.get("action_id", action.get("name")))
        if not isinstance(action_id, str) or not action_id:
            raise FeishuProtocolError("card action_id is required")
        form_value = action.get("form_value", event.get("form_value"))
        return CardInteractionEvent(
            event_id=event_id,
            external_tenant_id=self._string_or_none(header.get("tenant_key")),
            external_user_id=open_id,
            external_message_id=None,
            occurred_at=self._timestamp(header.get("create_time")),
            message_id=self._required_string(context, "open_message_id"),
            action_id=action_id,
            action_value=value_object,
            form_values=form_value if isinstance(form_value, dict) else {},
        )

    def _parse_legacy_card(self, payload: JsonObject) -> CardInteractionEvent:
        action = payload.get("action")
        if not isinstance(action, dict):
            raise UnsupportedInboundEventError("unsupported Feishu event")
        value = action.get("value")
        value_object: JsonObject = dict(value) if isinstance(value, dict) else {}
        action_id = value_object.pop("action_id", action.get("action_id", action.get("name")))
        if not isinstance(action_id, str):
            raise FeishuProtocolError("card action_id is required")
        open_id = payload.get("open_id")
        if not isinstance(open_id, str):
            raise FeishuProtocolError("card operator open_id is required")
        return CardInteractionEvent(
            event_id=self._required_string(payload, "event_id"),
            external_tenant_id=self._string_or_none(payload.get("tenant_key")),
            external_user_id=open_id,
            external_message_id=None,
            occurred_at=None,
            message_id=self._required_string(payload, "open_message_id"),
            action_id=action_id,
            action_value=value_object,
            form_values={},
        )

    @staticmethod
    def _required_string(source: object, key: str) -> str:
        value = source.get(key) if isinstance(source, dict) else None
        if not isinstance(value, str) or not value:
            raise FeishuProtocolError(f"{key} is required")
        return value

    @staticmethod
    def _string_or_none(value: JsonValue) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _timestamp(value: JsonValue) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            timestamp = int(value)
            if timestamp > 10_000_000_000:
                timestamp //= 1000
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (ValueError, OSError):
            return None
