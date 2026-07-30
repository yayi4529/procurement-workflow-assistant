from typing import assert_type

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.domain.assistant_session import AgentSessionStateUpdate
from procurement_platform.domain.enums import AgentMessageSender, PlatformType, RoleCode
from procurement_platform.domain.errors import UserDisabledError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.user import CurrentUser, UserRole
from procurement_platform.ports.backend_client import BackendClient


def fake() -> FakeBackendClient:
    return FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="测试用户",
            mobile=None,
            status="ACTIVE",
            roles=(UserRole(role_code=RoleCode.APPLICANT),),
            buildings=(),
        )
    )


def identity() -> PlatformIdentity:
    return PlatformIdentity(PlatformType.TEST_PLATFORM, "test-user", "request")


def test_fake_conforms_to_protocol_statically() -> None:
    backend: BackendClient = fake()
    assert_type(backend, BackendClient)


@pytest.mark.asyncio
async def test_fake_supports_idempotency_pagination_state_snapshot_and_completion() -> None:
    backend = fake()
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity(), current_action="CARD_HELP"
    )
    first = await backend.append_agent_message(
        identity=identity(),
        conversation_id=conversation.conversation_id,
        external_message_id="message-1",
        sender_type=AgentMessageSender.USER,
        content="hello",
    )
    duplicate = await backend.append_agent_message(
        identity=identity(),
        conversation_id=conversation.conversation_id,
        external_message_id="message-1",
        sender_type=AgentMessageSender.USER,
        content="ignored",
    )
    page = await backend.list_agent_messages(
        identity=identity(), conversation_id=conversation.conversation_id
    )
    saved = await backend.update_agent_state(
        identity=identity(),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(current_action="CARD_HELP"),
    )
    state = await backend.get_agent_state(
        identity=identity(), conversation_id=conversation.conversation_id
    )
    snapshot = await backend.snapshot_agent_state(
        identity=identity(),
        conversation_id=conversation.conversation_id,
        snapshot_reason="test",
    )
    completion = await backend.complete_agent_conversation(
        identity=identity(),
        conversation_id=conversation.conversation_id,
        purchase_request_id=None,
    )
    assert duplicate.message_id == first.message_id
    assert duplicate.duplicate is True
    assert page.total == 1
    assert saved.expires_in_seconds == state.expires_in_seconds
    assert snapshot in backend.snapshots
    assert completion.redis_state_deleted is True
    assert backend.call_counts["append_agent_message"] == 2


@pytest.mark.asyncio
async def test_fake_supports_error_injection() -> None:
    backend = fake()
    backend.inject_error(
        "get_current_user",
        UserDisabledError("USER_DISABLED", "disabled"),
    )
    with pytest.raises(UserDisabledError):
        await backend.get_current_user(identity=identity())
