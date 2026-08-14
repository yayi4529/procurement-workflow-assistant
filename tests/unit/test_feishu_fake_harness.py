import json
import logging
from pathlib import Path

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.backend.fake_seed import FakeBackendSeedLoader
from procurement_platform.adapters.feishu.fake_client import FakeFeishuClient
from procurement_platform.application.inbound.message_handler import BaseMessageHandler
from procurement_platform.application.notifications.development_renderer import (
    DevelopmentNotificationPayload,
    DevelopmentNotificationRenderer,
)
from procurement_platform.application.notifications.workflow_assignment_renderer import (
    WorkflowAssignmentRenderer,
)
from procurement_platform.bootstrap.logging import JsonFormatter, mask_platform_user_id
from procurement_platform.bootstrap.settings import Settings
from procurement_platform.domain.assistant import (
    AssistantClarificationResponse,
    AssistantOption,
    AssistantTextResponse,
)
from procurement_platform.domain.assistant_errors import LlmTimeoutError
from procurement_platform.domain.enums import BackendMode, PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.notification import (
    InteractionNotification,
    NotificationGatewayRequest,
)


class StubAssistant:
    def __init__(self, response: AssistantTextResponse | AssistantClarificationResponse) -> None:
        self._response = response

    async def handle(self, event: TextMessageEvent):
        del event
        return self._response


class FailingAssistant:
    async def handle(self, event: TextMessageEvent):
        del event
        raise LlmTimeoutError("timeout")


class StubLock:
    def acquire(self, *, key: str):
        del key
        return self

    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb


def fake_environment(**overrides: str) -> dict[str, str]:
    values = {
        "PROCUREMENT_ENVIRONMENT": "development",
        "PROCUREMENT_BACKEND_MODE": "fake",
        "PROCUREMENT_FAKE_DATA_PATH": "example.json",
    }
    values.update(overrides)
    return values


def test_fake_settings_do_not_require_http_backend_credentials() -> None:
    settings = Settings.from_env(fake_environment())
    assert settings.backend_mode is BackendMode.FAKE
    assert settings.backend_base_url == "http://unused.invalid"
    with pytest.raises(ValueError, match="forbidden"):
        Settings.from_env(fake_environment(PROCUREMENT_ENVIRONMENT="production"))


@pytest.mark.asyncio
async def test_seed_loader_and_identity_mapping(tmp_path: Path) -> None:
    path = tmp_path / "seed.json"
    path.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "platform_user_id": "ou_applicant",
                        "employee_id": 1001,
                        "name": "需求人",
                        "roles": ["APPLICANT"],
                        "buildings": [
                            {
                                "building_id": 1,
                                "building_name": "一号楼",
                                "is_primary": True,
                            }
                        ],
                    },
                    {
                        "platform_user_id": "ou_manager",
                        "employee_id": 2001,
                        "name": "楼长",
                        "roles": ["BUILDING_MANAGER"],
                        "buildings": [
                            {
                                "building_id": 1,
                                "building_name": "一号楼",
                                "is_primary": True,
                            }
                        ],
                    },
                    {
                        "platform_user_id": "ou_purchaser",
                        "employee_id": 3001,
                        "name": "采购员",
                        "roles": ["PURCHASER"],
                        "buildings": [],
                    },
                    {
                        "platform_user_id": "ou_warehouse",
                        "employee_id": 4001,
                        "name": "仓库",
                        "roles": ["WAREHOUSE_MANAGER"],
                        "buildings": [],
                    },
                ],
                "routing": {
                    "building_manager_by_building": {"1": [2001]},
                    "purchasers": [3001],
                    "warehouse_managers": [4001],
                },
                "suppliers": [{"supplier_id": 1, "supplier_name": "供应商"}],
            }
        ),
        encoding="utf-8",
    )
    seed = FakeBackendSeedLoader.load(path)
    backend = FakeBackendClient(users_by_platform_id=FakeBackendSeedLoader.users(seed))
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_manager")
    user = await backend.get_current_user(identity=identity)
    assert user.employee_id == 2001
    assert user.roles[0].role_code is RoleCode.BUILDING_MANAGER


@pytest.mark.asyncio
async def test_identity_probe_is_exact_and_returns_own_open_id() -> None:
    channel = FakeFeishuClient()
    handler = BaseMessageHandler(channel, debug_identity_probe_enabled=True)
    event = TextMessageEvent(
        event_id="evt",
        external_user_id="ou_abcdefghijk",
        external_message_id="om_1",
        text="调试身份",
    )
    await handler.handle(event)
    assert "ou_abcdefghijk" in channel.reply_text_calls[0][1]


@pytest.mark.asyncio
async def test_agent_text_reply_is_sent_as_interaction_card() -> None:
    channel = FakeFeishuClient()
    handler = BaseMessageHandler(
        channel,
        assistant_service=StubAssistant(AssistantTextResponse(text="请告诉我品牌。")),
        conversation_lock_manager=StubLock(),
    )
    await handler.handle(
        TextMessageEvent(
            event_id="evt-card",
            external_user_id="ou_user",
            external_message_id="om_card",
            text="继续",
        )
    )

    assert channel.reply_text_calls == []
    assert channel.reply_interaction_calls[0][1].title == "采购助手"
    assert "请告诉我品牌" in str(channel.reply_interaction_calls[0][1])


@pytest.mark.asyncio
async def test_agent_clarification_reply_is_sent_as_interaction_card() -> None:
    channel = FakeFeishuClient()
    response = AssistantClarificationResponse(
        question="请选择角色",
        options=(AssistantOption(label="需求人", value="APPLICANT"),),
    )
    handler = BaseMessageHandler(
        channel,
        assistant_service=StubAssistant(response),
        conversation_lock_manager=StubLock(),
    )
    await handler.handle(
        TextMessageEvent(
            event_id="evt-choice",
            external_user_id="ou_user",
            external_message_id="om_choice",
            text="开始",
        )
    )

    assert channel.reply_text_calls == []
    view = channel.reply_interaction_calls[0][1]
    assert view.title == "需要确认"
    assert "1. 需求人" in str(view)


@pytest.mark.asyncio
async def test_agent_timeout_is_returned_as_failure_card() -> None:
    channel = FakeFeishuClient()
    handler = BaseMessageHandler(
        channel,
        assistant_service=FailingAssistant(),
        conversation_lock_manager=StubLock(),
    )

    await handler.handle(
        TextMessageEvent(
            event_id="evt-timeout",
            external_user_id="ou_user",
            external_message_id="om_timeout",
            text="继续",
        )
    )

    assert len(channel.reply_interaction_calls) == 1
    view = channel.reply_interaction_calls[0][1]
    assert view.title == "处理失败"
    assert "响应超时" in str(view)


def test_development_notification_is_strict_and_marked() -> None:
    renderer = DevelopmentNotificationRenderer()
    result = renderer.render(
        NotificationGatewayRequest(
            notification_id=1,
            dedup_key="key",
            event_type="DEV_NOTIFICATION_TEST",
            platform_type=PlatformType.FEISHU,
            receiver_platform_user_id="ou_receiver",
            payload={
                "requirement_id": 1,
                "requirement_no": "DEV-1",
                "title": "测试",
            },
        )
    )
    assert isinstance(result, InteractionNotification)
    assert "【测试环境】" in result.view.title
    with pytest.raises(ValueError):
        DevelopmentNotificationPayload.model_validate(
            {
                "requirement_id": 1,
                "requirement_no": "DEV-1",
                "title": "测试",
                "secret": "must fail",
            }
        )


@pytest.mark.parametrize(
    ("event_type", "status", "status_label", "action_id"),
    (
        (
            "REQUIREMENT_PENDING_REVIEW",
            "PENDING_REVIEW",
            "待楼长审核",
            "building_manager.open_requirement",
        ),
        (
            "REQUIREMENT_PENDING_PURCHASE",
            "PENDING_PURCHASE",
            "待采购",
            "purchaser.open_requirement",
        ),
        (
            "REQUIREMENT_PENDING_WAREHOUSE",
            "PENDING_WAREHOUSE",
            "待入库",
            "warehouse.open_requirement",
        ),
    ),
)
def test_workflow_assignment_notification_opens_the_correct_role_card(
    event_type: str, status: str, status_label: str, action_id: str
) -> None:
    renderer = WorkflowAssignmentRenderer(event_type)
    result = renderer.render(
        NotificationGatewayRequest(
            notification_id=1,
            dedup_key="key",
            event_type=event_type,
            platform_type=PlatformType.FEISHU,
            receiver_platform_user_id="ou_receiver",
            payload={"requirement_id": 1, "requirement_no": "PR-1", "status": status},
        )
    )
    assert isinstance(result, InteractionNotification)
    assert status_label in str(result.view)
    assert status not in str(result.view)
    assert result.view.actions[0].action_id == action_id
    assert result.view.actions[0].value == {"requirement_id": 1}


def test_json_logging_and_masking_do_not_expose_full_id() -> None:
    record = logging.LogRecord("test", logging.INFO, "", 0, "message", (), None)
    record.masked_platform_user_id = mask_platform_user_id("ou_abcdefghijk")
    encoded = JsonFormatter().format(record)
    assert json.loads(encoded)["message"] == "message"
    assert "ou_abcdefghijk" not in encoded
