# ruff: noqa: RUF001

from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.assistant.agents.applicant import ApplicantAgent
from procurement_platform.application.assistant.presentation import LegacyToolResultPresenter
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.task_context_service import AgentTaskStateService
from procurement_platform.application.assistant.tooling.multi_item import (
    DraftItemChange,
    UpdateMultiItemDraftArgs,
    UpdateMultiItemDraftTool,
)
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.application.assistant.workflow_state import (
    WorkflowRunState,
    WorkflowStateService,
)
from procurement_platform.application.multi_item_presenter import multi_item_markdown
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantToolContext,
)
from procurement_platform.domain.assistant_session import AgentSessionStateUpdate
from procurement_platform.domain.enums import (
    PurchaseItemKind,
    RequestType,
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import SelectInput, TextInput
from procurement_platform.domain.requirement import ApplicantFields, PurchaseRecord
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
async def test_detached_persisted_items_are_not_reused_for_new_requirement() -> None:
    backend = FakeBackendClient(_user())
    identity = PlatformIdentity.create("TEST_PLATFORM", "ou_task06b")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    tool = UpdateMultiItemDraftTool(backend)
    first = await tool.execute(
        args=UpdateMultiItemDraftArgs(
            operation="REPLACE",
            request_type=RequestType.PURCHASE,
            application_reason="旧草稿",
            items=(
                DraftItemChange(
                    item_kind=PurchaseItemKind.COMPONENT,
                    item_name="旧蓄电池",
                    quantity="1",
                    unit="块",
                ),
            ),
        ),
        context=_context(conversation.conversation_id),
    )
    assert first.items[0].request_item_id is not None
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    detached = AgentSessionStateUpdate.model_validate(
        state.model_dump(
            exclude={"conversation_id", "expires_in_seconds", "restored_from_snapshot"}
        )
    ).model_copy(update={"purchase_request_id": None})
    await backend.update_agent_state(
        identity=identity,
        conversation_id=conversation.conversation_id,
        state=detached,
    )

    result = await tool.execute(
        args=UpdateMultiItemDraftArgs(
            operation="ADD",
            request_type=RequestType.PURCHASE,
            application_reason="新草稿",
            items=(
                DraftItemChange(
                    item_kind=PurchaseItemKind.COMPONENT,
                    item_name="UPS蓄电池",
                    quantity="3",
                    unit="块",
                ),
            ),
        ),
        context=_context(conversation.conversation_id),
    )

    assert result.status == "SUCCESS"
    assert [item.item_name for item in result.items] == ["UPS蓄电池"]
    assert result.requirement_id != first.requirement_id


@pytest.mark.asyncio
async def test_start_new_clears_persisted_item_ids_from_previous_requirement() -> None:
    backend = FakeBackendClient(_user())
    identity = PlatformIdentity.create("TEST_PLATFORM", "ou_task06b")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    tool = UpdateMultiItemDraftTool(backend)
    first = await tool.execute(
        args=UpdateMultiItemDraftArgs(
            operation="REPLACE",
            request_type=RequestType.PURCHASE,
            application_reason="旧草稿",
            items=(
                DraftItemChange(
                    item_kind=PurchaseItemKind.EQUIPMENT,
                    item_name="旧环境检测仪",
                    quantity="1",
                    unit="台",
                ),
            ),
        ),
        context=_context(conversation.conversation_id),
    )
    assert first.items[0].request_item_id is not None

    result = await tool.execute(
        args=UpdateMultiItemDraftArgs(
            operation="ADD",
            start_new=True,
            request_type=RequestType.PURCHASE,
            application_reason="新采购需求",
            items=(
                DraftItemChange(
                    item_kind=PurchaseItemKind.EQUIPMENT,
                    item_name="环境检测仪",
                    quantity="2",
                    unit="台",
                ),
            ),
        ),
        context=_context(conversation.conversation_id, first.requirement_id),
    )

    assert result.status == "SUCCESS"
    assert result.requirement_id != first.requirement_id
    assert [item.item_name for item in result.items] == ["环境检测仪"]
    assert result.items[0].request_item_id is not None
    assert result.items[0].request_item_id != first.items[0].request_item_id


@pytest.mark.asyncio
async def test_new_multi_item_auto_creates_when_session_focus_is_submitted() -> None:
    backend = FakeBackendClient(_user())
    identity = PlatformIdentity.create("TEST_PLATFORM", "ou_task06b")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    submitted = await backend.create_requirement(identity=identity, building_id=1)
    submitted_detail = await backend.get_requirement(
        identity=identity, requirement_id=submitted.requirement_id
    )
    backend.seed_requirement(
        submitted_detail.model_copy(update={"status": RequirementStatus.PENDING_REVIEW})
    )

    result = await UpdateMultiItemDraftTool(backend).execute(
        args=UpdateMultiItemDraftArgs(
            operation="REPLACE",
            request_type=RequestType.PURCHASE,
            items=(
                DraftItemChange(
                    item_kind=PurchaseItemKind.EQUIPMENT,
                    item_name="开关电源",
                    quantity="2",
                    unit="台",
                ),
            ),
        ),
        context=_context(conversation.conversation_id, submitted.requirement_id),
    )

    assert result.status == "SUCCESS"
    assert result.requirement_id != submitted.requirement_id
    assert [item.item_name for item in result.items] == ["开关电源"]


@pytest.mark.asyncio
async def test_create_draft_save_phase_ignores_explicit_stale_requirement_id() -> None:
    backend = FakeBackendClient(_user())
    identity = PlatformIdentity.create("TEST_PLATFORM", "ou_task06b")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    submitted = await backend.create_requirement(identity=identity, building_id=1)
    submitted_detail = await backend.get_requirement(
        identity=identity, requirement_id=submitted.requirement_id
    )
    backend.seed_requirement(
        submitted_detail.model_copy(update={"status": RequirementStatus.PENDING_REVIEW})
    )
    workflow = WorkflowRunState(
        role=RoleCode.APPLICANT,
        skill_name="applicant",
        workflow_name="create-draft",
        phase="save-draft",
    )
    await WorkflowStateService(backend).save(
        identity=identity,
        conversation_id=conversation.conversation_id,
        session=None,
        workflow=workflow,
    )

    result = await UpdateMultiItemDraftTool(backend).execute(
        args=UpdateMultiItemDraftArgs(
            requirement_id=submitted.requirement_id,
            operation="REPLACE",
            request_type=RequestType.PURCHASE,
            application_reason="之前的风扇坏了",
            items=(
                DraftItemChange(
                    item_kind=PurchaseItemKind.COMPONENT,
                    item_name="冷却风扇",
                    quantity="2",
                    unit="个",
                    brand="Vertiv",
                    model="HF-E200-25",
                ),
            ),
        ),
        context=_context(conversation.conversation_id, submitted.requirement_id),
    )

    assert result.status == "SUCCESS"
    assert result.requirement_id != submitted.requirement_id
    assert result.fields_complete is True
    assert result.items[0].brand == "Vertiv"
    assert result.items[0].model == "HF-E200-25"


@pytest.mark.asyncio
async def test_multi_item_draft_fills_device_profession_from_history() -> None:
    backend = FakeBackendClient(_user())
    identity = PlatformIdentity.create("TEST_PLATFORM", "ou_task06b")
    historical = await backend.create_requirement(identity=identity, building_id=1)
    historical_detail = await backend.get_requirement(
        identity=identity, requirement_id=historical.requirement_id
    )
    backend.seed_requirement(
        historical_detail.model_copy(
            update={
                "status": RequirementStatus.COMPLETED,
                "applicant_fields": ApplicantFields(
                    device_profession="电气",
                    device_name="控制电源",
                    quantity="1",
                    unit="个",
                    application_reason="历史采购",
                ),
            }
        )
    )
    backend.purchase_records.append(
        PurchaseRecord(
            requirement_id=historical.requirement_id,
            requirement_no=historical.requirement_no,
            device_profession="电气",
            device_name="控制电源",
            status=RequirementStatus.COMPLETED,
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
    )
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )

    result = await UpdateMultiItemDraftTool(backend).execute(
        args=UpdateMultiItemDraftArgs(
            operation="REPLACE",
            start_new=True,
            request_type=RequestType.PURCHASE,
            application_reason="新增控制电源",
            items=(
                DraftItemChange(
                    item_kind=PurchaseItemKind.COMPONENT,
                    item_name="控制电源",
                    quantity="1",
                ),
            ),
        ),
        context=_context(conversation.conversation_id),
    )

    assert result.requirement_id is not None
    saved = await backend.get_requirement(identity=identity, requirement_id=result.requirement_id)
    assert saved.applicant_fields.device_profession == "电气"
    assert result.items[0].unit == "个"


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


@pytest.mark.asyncio
async def test_single_agent_presenter_returns_new_multi_item_confirmation_card() -> None:
    backend = FakeBackendClient(_user())
    identity = PlatformIdentity.create("TEST_PLATFORM", "ou_task06b_presenter")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    context = _context(conversation.conversation_id)
    result = await UpdateMultiItemDraftTool(backend).execute(
        args=UpdateMultiItemDraftArgs(
            operation="REPLACE",
            start_new=True,
            request_type=RequestType.MAINTENANCE,
            application_reason="2号UPS电池故障更换",
            items=(
                DraftItemChange(
                    item_kind=PurchaseItemKind.COMPONENT,
                    item_name="南都蓄电池",
                    brand="南都",
                    model="2V 100Ah",
                    quantity="3",
                    unit="块",
                ),
            ),
        ),
        context=context,
    )
    response = await LegacyToolResultPresenter(
        backend_client=backend,
        session_service=AssistantSessionService(backend),
    ).present(
        result=result,
        context=context,
        external_message_id=context.external_message_id,
    )

    assert isinstance(response, AssistantInteractionResponse)
    assert response.view.title == "采购申请详情"
    assert "南都蓄电池" in str(response.view)
    assert any(isinstance(item, TextInput) for item in response.view.elements)
    inputs = {
        item.name: item for item in response.view.elements if isinstance(item, TextInput)
    }
    assert inputs["device_name"].default_value == "南都蓄电池"
    assert inputs["brand"].default_value == "南都"
    assert inputs["model"].default_value == "2V 100Ah"
    assert inputs["quantity"].default_value == "3"
    assert inputs["unit"].default_value == "块"
    assert inputs["application_reason"].default_value == "2号UPS电池故障更换"
    item_kind = next(
        item
        for item in response.view.elements
        if isinstance(item, SelectInput) and item.name == "item_kind"
    )
    assert item_kind.default_value == "COMPONENT"
    assert {action.action_id for action in response.view.actions} == {
        "applicant.prepare_submit",
        "applicant.list",
    }
    assert all("新增采购项" not in str(item) for item in response.view.elements)


def test_multi_item_args_reject_non_positive_quantity() -> None:
    with pytest.raises(ValueError):
        DraftItemChange(quantity="0")
