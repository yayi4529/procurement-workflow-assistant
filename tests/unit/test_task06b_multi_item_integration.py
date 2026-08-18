# ruff: noqa: RUF001

from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.assistant.agents.applicant import ApplicantAgent
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.task_context_service import AgentTaskStateService
from procurement_platform.application.assistant.tooling.multi_item import (
    DraftItemChange,
    UpdateMultiItemDraftArgs,
    UpdateMultiItemDraftTool,
)
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.application.multi_item_presenter import multi_item_markdown
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantToolContext,
)
from procurement_platform.domain.enums import (
    PurchaseItemKind,
    RequestType,
    RoleCode,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import TextInput
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def _user() -> CurrentUser:
    return CurrentUser(
        employee_id=1,
        name="申请人",
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=RoleCode.APPLICANT),),
        buildings=(UserBuilding(building_id=1, building_name="一号楼", is_primary=True),),
    )


def _context(conversation_id: int, requirement_id: int | None = None) -> AssistantToolContext:
    return AssistantToolContext(
        platform_type="TEST_PLATFORM",
        platform_user_id="ou_task06b",
        conversation_id=conversation_id,
        external_conversation_id="oc_task06b",
        external_message_id=f"om_{datetime.now(UTC).timestamp()}",
        current_time=datetime(2026, 8, 18, tzinfo=UTC),
        timezone_name="Asia/Shanghai",
        current_user=_user(),
        active_requirement_id=requirement_id,
    )


@pytest.mark.asyncio
async def test_multi_item_draft_replace_update_remove_keeps_stable_ids() -> None:
    backend = FakeBackendClient(_user())
    identity = PlatformIdentity.create("TEST_PLATFORM", "ou_task06b")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    tool = UpdateMultiItemDraftTool(backend)
    created = await tool.execute(
        args=UpdateMultiItemDraftArgs(
            operation="REPLACE",
            request_type=RequestType.MAINTENANCE,
            application_reason="UPS 电池维护",
            items=(
                DraftItemChange(
                    item_kind=PurchaseItemKind.COMPONENT,
                    item_name="蓄电池",
                    quantity="3",
                    unit="块",
                ),
                DraftItemChange(
                    item_kind=PurchaseItemKind.MATERIAL,
                    item_name="连接件",
                    quantity="3",
                    unit="个",
                ),
                DraftItemChange(
                    item_kind=PurchaseItemKind.SERVICE,
                    item_name="检测服务",
                    quantity="1",
                    unit="次",
                ),
            ),
        ),
        context=_context(conversation.conversation_id),
    )
    assert created.status == "SUCCESS"
    assert [item.draft_item_id for item in created.items] == [
        "draft-item-1",
        "draft-item-2",
        "draft-item-3",
    ]
    assert created.items[2].requires_warehouse is None
    requirement_id = created.requirement_id
    assert requirement_id is not None

    updated = await tool.execute(
        args=UpdateMultiItemDraftArgs(
            operation="UPDATE",
            target_draft_item_id="draft-item-2",
            items=(DraftItemChange(quantity="4"),),
        ),
        context=_context(conversation.conversation_id, requirement_id),
    )
    assert [item.quantity for item in updated.items] == ["3", "4", "1"]
    removed = await tool.execute(
        args=UpdateMultiItemDraftArgs(operation="REMOVE", target_draft_item_id="draft-item-3"),
        context=_context(conversation.conversation_id, requirement_id),
    )
    assert [item.draft_item_id for item in removed.items] == [
        "draft-item-1",
        "draft-item-2",
    ]
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    task = AgentTaskStateService.from_session(state)
    assert state.purchase_request_id == requirement_id
    assert task.request_draft is not None
    assert task.request_draft.request_type is RequestType.MAINTENANCE
    detail = await backend.get_requirement(identity=identity, requirement_id=requirement_id)
    assert [item.item_name for item in detail.items] == ["蓄电池", "连接件"]
    assert "品牌/型号：未指定" in multi_item_markdown(detail)


@pytest.mark.asyncio
async def test_complete_multi_item_result_returns_formal_confirmation_card() -> None:
    backend = FakeBackendClient(_user())
    identity = PlatformIdentity.create("TEST_PLATFORM", "ou_task06b_card")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    context = _context(conversation.conversation_id)
    tool = UpdateMultiItemDraftTool(backend)
    result = await tool.execute(
        args=UpdateMultiItemDraftArgs(
            operation="REPLACE",
            request_type=RequestType.MAINTENANCE,
            application_reason="机房扩容",
            items=(
                DraftItemChange(
                    item_kind=PurchaseItemKind.MATERIAL,
                    item_name="服务器",
                    quantity="2",
                    unit="台",
                ),
            ),
        ),
        context=context,
    )
    agent = ApplicantAgent(
        backend_client=backend,
        llm_client=FakeLlmClient(turns=()),
        session_service=AssistantSessionService(backend),
        tool_executor=ToolExecutor(ToolRegistry(), max_result_chars=20000),
    )
    response = await agent.handle_tool_result(
        result=result,
        context=context,
        external_message_id=context.external_message_id,
    )
    assert response is not None
    assert isinstance(response, AssistantInteractionResponse)
    assert response.view.title == "采购申请确认"
    assert not any(isinstance(item, TextInput) for item in response.view.elements)
    assert "服务器" in str(response.view)


def test_multi_item_args_reject_non_positive_quantity() -> None:
    with pytest.raises(ValueError):
        DraftItemChange(quantity="0")
