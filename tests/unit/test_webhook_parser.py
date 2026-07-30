import json

import pytest

from procurement_platform.adapters.feishu.webhook_parser import (
    ChallengeResponse,
    FeishuWebhookParser,
)
from procurement_platform.domain.errors import FeishuProtocolError, FeishuVerificationError
from procurement_platform.domain.inbound_event import CardInteractionEvent, TextMessageEvent


def parser() -> FeishuWebhookParser:
    return FeishuWebhookParser(verification_token="verify")


def test_challenge_and_private_text() -> None:
    challenge = parser().parse(body=json.dumps({"token": "verify", "challenge": "answer"}).encode())
    assert challenge == ChallengeResponse("answer")
    event = parser().parse(
        body=json.dumps(
            {
                "header": {
                    "token": "verify",
                    "event_id": "event-1",
                    "event_type": "im.message.receive_v1",
                    "tenant_key": "tenant",
                    "create_time": "1700000000",
                },
                "event": {
                    "sender": {"sender_id": {"open_id": "ou_user"}},
                    "message": {
                        "message_id": "om_message",
                        "message_type": "text",
                        "chat_type": "p2p",
                        "chat_id": "chat",
                        "content": json.dumps({"text": " hi "}),
                    },
                },
            }
        ).encode()
    )
    assert isinstance(event, TextMessageEvent)
    assert event.text == "hi"


def test_parser_rejects_bad_token_and_empty_text() -> None:
    with pytest.raises(FeishuVerificationError):
        parser().parse(body=b'{"token":"bad","challenge":"x"}')
    payload = {
        "header": {
            "token": "verify",
            "event_id": "e",
            "event_type": "im.message.receive_v1",
        },
        "event": {
            "sender": {"sender_id": {"open_id": "u"}},
            "message": {
                "message_id": "m",
                "message_type": "text",
                "chat_type": "p2p",
                "content": '{"text":" "}',
            },
        },
    }
    with pytest.raises(FeishuProtocolError):
        parser().parse(body=json.dumps(payload).encode())


def test_card_action_uses_callback_operator_identity() -> None:
    event = parser().parse(
        body=json.dumps(
            {
                "header": {
                    "token": "verify",
                    "event_id": "card-1",
                    "event_type": "card.action.trigger",
                },
                "event": {
                    "operator": {"open_id": "ou_operator"},
                    "context": {"open_message_id": "om_card"},
                    "action": {
                        "value": {
                            "action_id": "foundation.echo",
                            "reference": "safe",
                        },
                        "form_value": {"field": "value"},
                    },
                },
            }
        ).encode()
    )
    assert isinstance(event, CardInteractionEvent)
    assert event.external_user_id == "ou_operator"
    assert event.action_value == {"reference": "safe"}
