import json

from fastapi.testclient import TestClient
from pydantic import SecretStr

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.feishu.fake_client import FakeFeishuClient
from procurement_platform.adapters.feishu.webhook_parser import FeishuWebhookParser
from procurement_platform.adapters.persistence.memory_event_dedup_store import (
    MemoryEventDedupStore,
)
from procurement_platform.adapters.persistence.memory_notification_delivery_store import (
    MemoryNotificationDeliveryStore,
)
from procurement_platform.application.inbound.card_interaction_handler import (
    BaseCardInteractionHandler,
)
from procurement_platform.application.inbound.message_handler import BaseMessageHandler
from procurement_platform.application.notifications.gateway_service import (
    NotificationGatewayService,
)
from procurement_platform.application.notifications.renderer_registry import (
    NotificationRendererRegistry,
)
from procurement_platform.bootstrap.container import ApplicationContainer
from procurement_platform.bootstrap.settings import (
    FeishuSettings,
    NotificationGatewaySettings,
    Settings,
)
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.notification import (
    NotificationGatewayRequest,
    TextNotification,
)
from procurement_platform.domain.user import CurrentUser, UserRole
from procurement_platform.interfaces.http.app import create_app


class HttpTestRenderer:
    event_type = "test.http"

    def render(self, request: NotificationGatewayRequest) -> TextNotification:
        return TextNotification(text=str(request.payload["text"]))


def configured_app() -> tuple[TestClient, FakeFeishuClient]:
    settings = Settings(
        environment="test",
        service_name="test",
        backend_base_url="http://backend",
        backend_request_timeout_seconds=1,
        identity_gateway_secret=SecretStr("identity"),
        allow_test_platform=True,
        feishu=FeishuSettings(
            enabled=True,
            app_id="app",
            app_secret=SecretStr("secret"),
            verification_token=SecretStr("verify"),
            webhook_path="/custom/feishu",
        ),
        notification_gateway=NotificationGatewaySettings(
            enabled=True,
            path="/custom/notifications",
            bearer_token=SecretStr("gateway"),
        ),
    )
    backend = FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="test",
            mobile=None,
            status="ACTIVE",
            roles=(UserRole(role_code=RoleCode.APPLICANT),),
            buildings=(),
        )
    )
    fake = FakeFeishuClient()
    registry = NotificationRendererRegistry()
    registry.register(HttpTestRenderer())
    delivery_store = MemoryNotificationDeliveryStore()
    container = ApplicationContainer(
        settings=settings,
        backend_client=backend,
        channel_client=fake,
        webhook_parser=FeishuWebhookParser(verification_token="verify"),
        event_dedup_store=MemoryEventDedupStore(),
        message_handler=BaseMessageHandler(fake),
        card_interaction_handler=BaseCardInteractionHandler(fake),
        notification_delivery_store=delivery_store,
        notification_renderer_registry=registry,
        notification_gateway_service=NotificationGatewayService(
            channel_client=fake,
            delivery_store=delivery_store,
            renderer_registry=registry,
            bearer_token="gateway",
        ),
    )
    return TestClient(create_app(settings, container)), fake


def test_webhook_challenge_message_and_duplicate() -> None:
    client, fake = configured_app()
    with client:
        response = client.post(
            "/custom/feishu",
            json={"token": "verify", "challenge": "answer"},
        )
        assert response.json() == {"challenge": "answer"}
        payload = {
            "header": {
                "token": "verify",
                "event_id": "e1",
                "event_type": "im.message.receive_v1",
            },
            "event": {
                "sender": {"sender_id": {"open_id": "ou"}},
                "message": {
                    "message_id": "om",
                    "message_type": "text",
                    "chat_type": "p2p",
                    "content": json.dumps({"text": "hello"}),
                },
            },
        }
        assert client.post("/custom/feishu", json=payload).status_code == 200
        payload["header"]["event_id"] = "e2"
        assert client.post("/custom/feishu", json=payload).status_code == 200
    assert len(fake.reply_text_calls) == 1


def test_card_callback_returns_new_raw_card_response_shape() -> None:
    client, _ = configured_app()
    payload = {
        "header": {
            "token": "verify",
            "event_id": "card-event",
            "event_type": "card.action.trigger",
        },
        "event": {
            "operator": {"open_id": "ou"},
            "action": {"value": {"action_id": "foundation.echo"}},
            "context": {"open_message_id": "om_card"},
        },
    }
    with client:
        response = client.post("/custom/feishu", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["toast"]["type"] == "success"
    assert body["card"]["type"] == "raw"
    assert body["card"]["data"]["header"]["title"]["content"] == "基础链路验证"


def test_notification_gateway_delivers_once_and_validates_headers() -> None:
    client, fake = configured_app()
    body = {
        "notification_id": 7,
        "dedup_key": "key",
        "event_type": "test.http",
        "platform_type": "FEISHU",
        "receiver_platform_user_id": "ou_receiver",
        "payload": {"text": "notification"},
    }
    headers = {
        "Authorization": "Bearer gateway",
        "Idempotency-Key": "key",
        "X-Notification-Id": "7",
    }
    with client:
        assert client.post("/custom/notifications", json=body, headers=headers).status_code == 204
        assert client.post("/custom/notifications", json=body, headers=headers).status_code == 204
        assert (
            client.post(
                "/custom/notifications",
                json=body,
                headers={**headers, "Idempotency-Key": "wrong"},
            ).status_code
            == 400
        )
    assert len(fake.send_text_calls) == 1
