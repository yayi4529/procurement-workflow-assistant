# ruff: noqa: RUF001

import asyncio

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.assistant.agent import ProcurementAgent
from procurement_platform.application.assistant.capabilities import (
    DEFAULT_CAPABILITY_METADATA,
    CapabilityPolicy,
)
from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.presentation import LegacyToolResultPresenter
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.service import (
    AssistantService,
    FaultGuidanceHandler,
)
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantTextResponse,
    AssistantTurn,
)
from procurement_platform.domain.enums import (
    AgentMessageSender,
    FaultAction,
    PlatformType,
    RoleCode,
)
from procurement_platform.domain.fault_guidance import FaultGuidanceResponse
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def _backend(*roles: RoleCode) -> FakeBackendClient:
    return FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="Multi",
            mobile=None,
            status="ACTIVE",
            roles=tuple(UserRole(role_code=role) for role in roles),
            buildings=(UserBuilding(building_id=1, building_name="一号楼", is_primary=True),),
        )
    )


def _service(
    backend: FakeBackendClient,
    *,
    turns: tuple[AssistantTurn, ...] = (),
    llm: FakeLlmClient | None = None,
    fault_guidance_service: FaultGuidanceHandler | None = None,
) -> AssistantService:
    sessions = AssistantSessionService(backend)
    registry = ToolRegistry()
    executor = ToolExecutor(registry, max_result_chars=1000)
    runtime = AssistantRuntime(
        llm_client=llm or FakeLlmClient(turns=turns),
        tool_registry=registry,
        tool_executor=executor,
        max_tool_steps=2,
    )
    policy = CapabilityPolicy(DEFAULT_CAPABILITY_METADATA)
    agent = ProcurementAgent(
        runtime=runtime,
        capability_policy=policy,
        session_service=sessions,
        result_presenter=LegacyToolResultPresenter(
            backend_client=backend,
            session_service=sessions,
        ),
    )
    return AssistantService(
        backend_client=backend,
        session_service=sessions,
        context_builder=AssistantContextBuilder(),
        procurement_agent=agent,
        max_history_messages=20,
        fault_guidance_service=fault_guidance_service,
    )


def _event(identifier: str, text: str) -> TextMessageEvent:
    return TextMessageEvent(
        event_id=f"event-{identifier}",
        external_user_id="ou_multi",
        external_message_id=identifier,
        chat_id="chat",
        text=text,
    )


@pytest.mark.asyncio
async def test_multi_role_text_does_not_require_role_selection() -> None:
    assistant = _service(
        _backend(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER),
        turns=(AssistantTurn(content="统一 Agent 可服务您的全部采购角色"),),
    )

    response = await assistant.handle(_event("m1", "解释多角色用户如何使用采购助手"))

    assert response == AssistantTextResponse(text="统一 Agent 可服务您的全部采购角色")
    assert not hasattr(assistant, "_agent_router")
    assert not hasattr(assistant, "_role_intent_resolver")


@pytest.mark.asyncio
async def test_focused_role_is_retained_but_does_not_gate_text_agent() -> None:
    backend = _backend(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER)
    assistant = _service(backend, turns=(AssistantTurn(content="仍使用统一 Agent"),))

    switch = await assistant.handle(_event("switch", "切换到楼长"))
    response = await assistant.handle(_event("m2", "再看看我自己最近申请的采购单"))

    assert switch == AssistantTextResponse(
        text="已将默认展示角色切换为楼长；可用能力仍包含您的全部采购角色。"
    )
    assert response == AssistantTextResponse(text="仍使用统一 Agent")
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_multi")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.focused_role is RoleCode.BUILDING_MANAGER


@pytest.mark.asyncio
async def test_single_role_uses_same_procurement_agent_path() -> None:
    assistant = _service(
        _backend(RoleCode.WAREHOUSE_MANAGER),
        turns=(AssistantTurn(content="已查询待入库采购单"),),
    )

    assert await assistant.handle(_event("warehouse", "查询待入库单")) == (
        AssistantTextResponse(text="已查询待入库采购单")
    )


@pytest.mark.asyncio
async def test_user_without_workflow_role_is_rejected_before_llm() -> None:
    assistant = _service(_backend(RoleCode.ADMIN), turns=())

    assert await assistant.handle(_event("admin", "查询采购单")) == AssistantTextResponse(
        text="当前身份没有可用的采购助手角色。"
    )


@pytest.mark.asyncio
async def test_duplicate_immediately_reuses_persisted_reply_without_llm() -> None:
    backend = _backend(RoleCode.APPLICANT)
    llm = FakeLlmClient(turns=(AssistantTurn(content="只执行一次"),))
    assistant = _service(backend, llm=llm)

    first = await assistant.handle(_event("same", "你好"))
    second = await assistant.handle(_event("same", "你好"))

    assert first == second == AssistantTextResponse(text="只执行一次")
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_duplicate_after_more_than_50_messages_uses_direct_lookup() -> None:
    backend = _backend(RoleCode.APPLICANT)
    llm = FakeLlmClient(turns=(AssistantTurn(content="旧回复"),))
    assistant = _service(backend, llm=llm)
    await assistant.handle(_event("old", "你好"))
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_multi")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    for index in range(60):
        await backend.append_agent_message(
            identity=identity,
            conversation_id=conversation.conversation_id,
            external_message_id=f"noise-{index}",
            sender_type=AgentMessageSender.USER,
            content="noise",
        )

    replay = await assistant.handle(_event("old", "你好"))

    assert replay == AssistantTextResponse(text="旧回复")
    assert len(llm.calls) == 1
    assert backend.call_counts["get_agent_message_by_external_id"] == 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_executes_llm_at_most_once() -> None:
    backend = _backend(RoleCode.APPLICANT)
    llm = FakeLlmClient(turns=(AssistantTurn(content="完成"),))
    assistant = _service(backend, llm=llm)

    responses = await asyncio.gather(
        assistant.handle(_event("race", "你好")),
        assistant.handle(_event("race", "你好")),
    )

    assert len(llm.calls) == 1
    assert AssistantTextResponse(text="完成") in responses
    assert all(item.text in {"完成", "该消息正在处理中，请稍候。"} for item in responses)


class StubFaultGuidance:
    def __init__(self, *responses: FaultGuidanceResponse, active: bool = False) -> None:
        self.responses = list(responses)
        self.active = active
        self.messages: list[str] = []

    async def start(self, conversation_id: int | str) -> None:
        del conversation_id
        self.active = True

    async def is_active(self, conversation_id: int | str) -> bool:
        del conversation_id
        return self.active

    async def handle_message(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        user_message: str,
    ) -> FaultGuidanceResponse:
        del identity, conversation_id
        self.messages.append(user_message)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_fault_guidance_explicit_entry_and_active_follow_up() -> None:
    fault = StubFaultGuidance(
        FaultGuidanceResponse(
            reply="具体是什么告警？",
            action=FaultAction.ASK,
        )
    )
    assistant = _service(
        _backend(RoleCode.APPLICANT),
        turns=(),
        fault_guidance_service=fault,
    )

    started = await assistant.handle(_event("fault-start", "故障引导"))
    response = await assistant.handle(_event("fault-next", "2号UPS最近老报警"))

    assert started == AssistantTextResponse(
        text="故障采购引导已开始，请描述资产和故障现象。例如：2号UPS最近老报警。"
    )
    assert response == AssistantTextResponse(text="具体是什么告警？")
    assert fault.messages == ["2号UPS最近老报警"]


@pytest.mark.asyncio
async def test_fault_guidance_prefix_routes_only_the_payload() -> None:
    fault = StubFaultGuidance(
        FaultGuidanceResponse(reply="之前是否检测过？", action=FaultAction.ASK)
    )
    assistant = _service(
        _backend(RoleCode.APPLICANT),
        turns=(),
        fault_guidance_service=fault,
    )

    response = await assistant.handle(_event("fault-prefix", "故障引导：2号UPS报BATTERY FAULT"))

    assert response == AssistantTextResponse(text="之前是否检测过？")
    assert fault.messages == ["2号UPS报BATTERY FAULT"]


@pytest.mark.asyncio
async def test_fault_draft_success_returns_existing_confirmation_card() -> None:
    backend = _backend(RoleCode.APPLICANT)
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_multi")
    summary = await backend.create_requirement(identity=identity, building_id=1)
    fault = StubFaultGuidance(
        FaultGuidanceResponse(
            reply="采购草稿已创建。",
            action=FaultAction.DIRECT_TO_PROCUREMENT,
            procurement_draft_ref=f"requirement:{summary.requirement_id}",
        )
    )
    assistant = _service(backend, turns=(), fault_guidance_service=fault)

    response = await assistant.handle(_event("fault-confirm", "故障引导：确认"))

    assert isinstance(response, AssistantInteractionResponse)
    assert response.view.title == "采购申请确认"
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.purchase_request_id == summary.requirement_id
