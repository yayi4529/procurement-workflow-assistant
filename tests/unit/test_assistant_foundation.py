import asyncio
from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.llm.echo_tool import EchoTool
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.adapters.llm.openai_compatible_llm_client import OpenAICompatibleLlmClient
from procurement_platform.adapters.persistence.local_conversation_lock import (
    LocalConversationLockManager,
)
from procurement_platform.application.assistant.agent_tools import (
    RecommendProductOptionsTool,
    UpdatePurchaseDraftResult,
    UpdatePurchaseDraftTool,
)
from procurement_platform.application.assistant.context_builder import (
    AssistantContextBuilder,
    _beijing_timezone,
)
from procurement_platform.application.assistant.procurement_assistant import ProcurementAssistant
from procurement_platform.application.assistant.prompt_builder import PromptBuilder
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantMessage,
    AssistantTextResponse,
    AssistantToolCall,
    AssistantToolContext,
    AssistantTurn,
)
from procurement_platform.domain.assistant_errors import LlmUnavailableError
from procurement_platform.domain.assistant_session import (
    AgentSessionStateUpdate,
    RecommendationReference,
)
from procurement_platform.domain.enums import PlatformType, RequirementStatus, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.requirement import (
    ApplicantFields,
    ProductRecommendation,
    ProductRecommendations,
    RequirementBuilding,
    RequirementDetail,
    RequirementHandler,
)
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


def test_openai_message_payload_preserves_preceding_assistant_tool_call() -> None:
    call = AssistantToolCall(id="call-1", name="echo_tool", arguments_json='{"text":"hello"}')

    payload = OpenAICompatibleLlmClient._message_payload(
        AssistantMessage(role="assistant", content=None, tool_calls=(call,))
    )

    assert payload == {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "echo_tool", "arguments": '{"text":"hello"}'},
            }
        ],
    }


def test_beijing_timezone_has_stable_eight_hour_offset() -> None:
    offset = datetime.now(_beijing_timezone()).utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 8 * 60 * 60


def test_purchase_query_intent_requires_query_tool_before_text_reply() -> None:
    allowed = frozenset({"query_purchase_requests", "update_purchase_draft"})

    assert (
        ProcurementAssistant._required_tool("请查询我的采购需求列表", allowed)
        == "query_purchase_requests"
    )
    assert (
        ProcurementAssistant._required_tool("我要购买一台服务器, 整理成草稿", allowed)
        == "update_purchase_draft"
    )
    assert (
        ProcurementAssistant._required_tool("请补充信息", allowed, active_requirement_id=123)
        == "update_purchase_draft"
    )
    assert ProcurementAssistant._required_tool("你好", allowed) is None
    assert ProcurementAssistant._required_tool("请提交采购需求", allowed) is None


@pytest.mark.asyncio
async def test_draft_intent_forces_tool_and_asks_only_next_field() -> None:
    backend = FakeBackendClient(user())
    registry = ToolRegistry()
    registry.register(UpdatePurchaseDraftTool(backend))
    llm = FakeLlmClient(
        turns=(
            AssistantTurn(content="我来帮您保存草稿。"),
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(
                        id="draft-call",
                        name="update_purchase_draft",
                        arguments_json=(
                            '{"device_name":"服务器","brand":"戴尔","application_reason":"扩容"}'
                        ),
                    ),
                )
            ),
        )
    )
    assistant = ProcurementAssistant(
        backend_client=backend,
        llm_client=llm,
        session_service=AssistantSessionService(backend),
        context_builder=AssistantContextBuilder(),
        prompt_builder=PromptBuilder(),
        tool_registry=registry,
        tool_executor=ToolExecutor(registry, max_result_chars=20000),
        tool_policy=ToolPolicy(),
        max_tool_steps=4,
        max_history_messages=20,
    )

    response = await assistant.handle(
        TextMessageEvent(
            event_id="draft-event",
            external_user_id="ou_test",
            external_message_id="draft-message",
            chat_id="draft-chat",
            text="我要购买一台戴尔服务器, 整理成草稿",
        )
    )

    assert not isinstance(response, AssistantInteractionResponse)
    assert response.text.count("请问") == 1
    assert "设备类型" in response.text
    assert "待补充字段" not in response.text
    assert backend.call_counts["update_applicant_fields"] == 1
    assert len(llm.calls) == 2


def _assistant(backend: FakeBackendClient, registry: ToolRegistry) -> ProcurementAssistant:
    return ProcurementAssistant(
        backend_client=backend,
        llm_client=FakeLlmClient(turns=()),
        session_service=AssistantSessionService(backend),
        context_builder=AssistantContextBuilder(),
        prompt_builder=PromptBuilder(),
        tool_registry=registry,
        tool_executor=ToolExecutor(registry, max_result_chars=20000),
        tool_policy=ToolPolicy(),
        max_tool_steps=4,
        max_history_messages=20,
    )


@pytest.mark.asyncio
async def test_explicit_new_draft_does_not_reuse_submitted_requirement() -> None:
    backend = FakeBackendClient(user())
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_test")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    backend.seed_requirement(
        RequirementDetail(
            requirement_id=1,
            requirement_no="PR-OLD",
            status=RequirementStatus.PENDING_REVIEW,
            version=2,
            building=RequirementBuilding(building_id=1, building_name="A"),
            current_handler=RequirementHandler(employee_id=2, name="Manager"),
            applicant_fields=ApplicantFields(device_name="旧设备"),
            missing_fields=(),
            allowed_actions=(),
        )
    )
    await backend.update_agent_state(
        identity=identity,
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(purchase_request_id=1),
    )
    registry = ToolRegistry()
    registry.register(UpdatePurchaseDraftTool(backend))
    llm = FakeLlmClient(
        turns=(
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(
                        id="new-draft",
                        name="update_purchase_draft",
                        arguments_json=(
                            '{"device_profession":"暖通","device_name":"精密空调",'
                            '"brand":"维谛","model":"P2",'
                            '"quantity":"2","unit":"台",'
                            '"application_reason":"机房制冷扩容"}'
                        ),
                    ),
                )
            ),
        )
    )
    assistant = ProcurementAssistant(
        backend_client=backend,
        llm_client=llm,
        session_service=AssistantSessionService(backend),
        context_builder=AssistantContextBuilder(),
        prompt_builder=PromptBuilder(),
        tool_registry=registry,
        tool_executor=ToolExecutor(registry, max_result_chars=20000),
        tool_policy=ToolPolicy(),
        max_tool_steps=4,
        max_history_messages=20,
    )

    response = await assistant.handle(
        TextMessageEvent(
            event_id="new-event",
            external_user_id="ou_test",
            external_message_id="new-message",
            chat_id="new-chat",
            text="帮我新建采购两台精密空调, 用于机房制冷扩容。",
        )
    )

    assert isinstance(response, AssistantInteractionResponse)
    assert backend.call_counts["create_requirement"] == 1
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.purchase_request_id != 1


@pytest.mark.asyncio
async def test_brand_missing_forces_history_recommendation_before_reply() -> None:
    backend = FakeBackendClient(user())
    conversation = await backend.get_or_create_agent_conversation(
        identity=PlatformIdentity.create(PlatformType.FEISHU, "ou_test"),
        current_action="ASSISTANT_CHAT",
    )
    backend.product_recommendations = ProductRecommendations(
        items=tuple(
            ProductRecommendation(
                brand=brand,
                model=model,
                historical_count=1,
                last_purchased_at=datetime(2026, 8, index, tzinfo=UTC),
            )
            for index, (brand, model) in enumerate(
                (("华为", "A"), ("华为", "B"), ("H3C", "C"), ("锐捷", "D")), start=1
            )
        )
    )
    detail = RequirementDetail(
        requirement_id=1,
        requirement_no="PR-1",
        status=RequirementStatus.DRAFT,
        version=1,
        building=RequirementBuilding(building_id=1, building_name="A"),
        current_handler=RequirementHandler(employee_id=1, name="Test"),
        applicant_fields=ApplicantFields(device_name="交换机"),
        missing_fields=("brand",),
        allowed_actions=(),
    )
    backend.seed_requirement(detail)
    await backend.update_agent_state(
        identity=PlatformIdentity.create(PlatformType.FEISHU, "ou_test"),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            purchase_request_id=1,
            missing_fields=("brand",),
            pending_field="brand",
            focused_field="brand",
        ),
    )
    registry = ToolRegistry()
    registry.register(UpdatePurchaseDraftTool(backend))
    registry.register(RecommendProductOptionsTool(backend))
    assistant = _assistant(backend, registry)
    result = UpdatePurchaseDraftResult(
        status="SUCCESS",
        requirement_id=1,
        requirement_version=1,
        updated_fields=("device_name",),
        updated_values={"device_name": "交换机"},
        missing_fields=("brand",),
        next_missing_field="brand",
        fields_complete=False,
    )
    response = await assistant._respond_to_draft_update(
        result=result,
        identity=PlatformIdentity.create(PlatformType.FEISHU, "ou_test"),
        context=context().model_copy(
            update={
                "conversation_id": conversation.conversation_id,
                "active_requirement_id": 1,
            }
        ),
        external_message_id="m1",
        allowed=frozenset({"update_purchase_draft", "recommend_product_options"}),
    )
    assert isinstance(response, AssistantTextResponse)
    assert "根据历史采购记录" in response.text
    assert response.text.count("华为") == 1
    assert "1. 华为" in response.text
    assert "2. H3C" in response.text
    assert "3. 锐捷" in response.text
    assert backend.call_counts["recommend_products"] == 1


@pytest.mark.asyncio
async def test_invalid_product_selection_is_rejected_without_saving() -> None:
    backend = FakeBackendClient(user())
    conversation = await backend.get_or_create_agent_conversation(
        identity=PlatformIdentity.create(PlatformType.FEISHU, "ou_test"),
        current_action="ASSISTANT_CHAT",
    )
    await backend.update_agent_state(
        identity=PlatformIdentity.create(PlatformType.FEISHU, "ou_test"),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            pending_field="brand",
            last_recommendations=tuple(
                RecommendationReference(
                    reference_id=f"product:{index}:x",
                    kind="PRODUCT_RECOMMENDATION",
                    label=str(index),
                )
                for index in range(1, 4)
            ),
        ),
    )
    registry = ToolRegistry()
    registry.register(UpdatePurchaseDraftTool(backend))
    response = await _assistant(backend, registry).handle(
        TextMessageEvent(
            event_id="e4",
            external_user_id="ou_test",
            external_message_id="m4",
            chat_id="c4",
            text="4",
        )
    )
    assert isinstance(response, AssistantTextResponse)
    assert response.text == "当前有 3 个推荐选项, 请回复 1、2、3, 或者直接告诉我您需要的品牌。"
    assert backend.call_counts["update_applicant_fields"] == 0


@pytest.mark.asyncio
async def test_short_answer_is_bound_to_pending_device_profession_without_llm() -> None:
    backend = FakeBackendClient(user())
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_test")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity,
        current_action="ASSISTANT_CHAT",
    )
    backend.seed_requirement(
        RequirementDetail(
            requirement_id=1,
            requirement_no="PR-1",
            status=RequirementStatus.DRAFT,
            version=1,
            building=RequirementBuilding(building_id=1, building_name="A"),
            current_handler=RequirementHandler(employee_id=1, name="Test"),
            applicant_fields=ApplicantFields(
                device_name="精密空调",
                quantity="2",
                unit="台",
                application_reason="机房制冷扩容",
            ),
            missing_fields=("device_profession",),
            allowed_actions=(),
        )
    )
    await backend.update_agent_state(
        identity=identity,
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            purchase_request_id=1,
            missing_fields=("device_profession",),
            pending_field="device_profession",
            focused_field="device_profession",
        ),
    )
    registry = ToolRegistry()
    registry.register(UpdatePurchaseDraftTool(backend))

    response = await _assistant(backend, registry).handle(
        TextMessageEvent(
            event_id="e5",
            external_user_id="ou_test",
            external_message_id="m5",
            chat_id="c5",
            text="暖通",
        )
    )

    assert isinstance(response, AssistantTextResponse)
    assert backend.call_counts["update_applicant_fields"] == 1
    saved = await backend.get_requirement(identity=identity, requirement_id=1)
    assert saved.applicant_fields.device_profession == "暖通"
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.pending_field == "brand"
