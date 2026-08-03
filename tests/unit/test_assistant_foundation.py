import asyncio

import pytest

from procurement_platform.adapters.llm.echo_tool import EchoTool
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.adapters.persistence.local_conversation_lock import (
    LocalConversationLockManager,
)
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.domain.assistant import (
    AssistantToolCall,
    AssistantToolContext,
    AssistantTurn,
)
from procurement_platform.domain.assistant_errors import LlmUnavailableError
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def user() -> CurrentUser:
    return CurrentUser(
        employee_id=1,
        name="Test",
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=RoleCode.APPLICANT, role_name="Applicant"),),
        buildings=(UserBuilding(building_id=1, building_name="A", is_primary=True),),
    )


def context() -> AssistantToolContext:
    from datetime import UTC, datetime

    return AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id="ou_test",
        conversation_id=1,
        external_conversation_id="oc_1",
        external_message_id="om_1",
        current_time=datetime.now(UTC),
        timezone_name="Asia/Shanghai",
        current_user=user(),
    )


@pytest.mark.asyncio
async def test_tool_executor_runs_echo_and_rejects_invalid_arguments() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())
    executor = ToolExecutor(registry, max_result_chars=1000)
    message = await executor.execute(
        name="echo_tool",
        arguments_json='{"text":"hello"}',
        tool_call_id="call-1",
        context=context(),
        allowed_names=frozenset({"echo_tool"}),
    )
    assert message.tool_call_id == "call-1"
    assert '"echoed_text":"hello"' in message.content
    invalid = await executor.execute(
        name="echo_tool",
        arguments_json="[]",
        tool_call_id="call-2",
        context=context(),
        allowed_names=frozenset({"echo_tool"}),
    )
    assert '"INVALID_ARGUMENTS"' in invalid.content


@pytest.mark.asyncio
async def test_fake_llm_preserves_turns_and_reports_exhaustion() -> None:
    client = FakeLlmClient(
        turns=(
            AssistantTurn(
                tool_calls=(AssistantToolCall(id="c", name="echo_tool", arguments_json="{}"),)
            ),
        )
    )
    first = await client.complete(messages=(), tools=())
    assert first.tool_calls[0].id == "c"
    with pytest.raises(LlmUnavailableError):
        await client.complete(messages=(), tools=())


@pytest.mark.asyncio
async def test_local_conversation_lock_serializes_one_user_and_allows_other_users() -> None:
    manager = LocalConversationLockManager()
    entered: list[str] = []
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()
    other_entered = asyncio.Event()

    async def same_first() -> None:
        async with manager.acquire(key="FEISHU:a"):
            entered.append("first")
            first_entered.set()
            await release_first.wait()

    async def same_second() -> None:
        await first_entered.wait()
        async with manager.acquire(key="FEISHU:a"):
            entered.append("second")
            second_entered.set()

    async def other_user() -> None:
        await first_entered.wait()
        async with manager.acquire(key="FEISHU:b"):
            other_entered.set()

    tasks = [asyncio.create_task(item()) for item in (same_first, same_second, other_user)]
    await other_entered.wait()
    assert not second_entered.is_set()
    release_first.set()
    await asyncio.gather(*tasks)
    assert entered == ["first", "second"]
    assert manager._locks == {}
