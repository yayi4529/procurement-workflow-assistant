import asyncio
import json
from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.llm.echo_tool import EchoTool
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.adapters.llm.openai_compatible_llm_client import OpenAICompatibleLlmClient
from procurement_platform.adapters.persistence.local_conversation_lock import (
    LocalConversationLockManager,
)
from procurement_platform.application.assistant.agent_router import AgentRouter
from procurement_platform.application.assistant.agent_tools import (
    QueryPurchaseRequestsTool,
    RecommendProductOptionsTool,
    UpdatePurchaseDraftResult,
    UpdatePurchaseDraftTool,
)
from procurement_platform.application.assistant.agents.applicant import ApplicantAgent
from procurement_platform.application.assistant.context_builder import (
    AssistantContextBuilder,
    _beijing_timezone,
)
from procurement_platform.application.assistant.procurement_assistant import ProcurementAssistant
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.service import AssistantService
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
from procurement_platform.domain.assistant_session import AgentSessionStateUpdate
from procurement_platform.domain.enums import (
    AgentMessageSender,
    PlatformType,
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.requirement import (
    ApplicantFields,
    ProductRecommendation,
    ProductRecommendations,
    PurchaseRecord,
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


def _assistant(
    backend: FakeBackendClient,
    registry: ToolRegistry,
    llm: FakeLlmClient | None = None,
) -> ProcurementAssistant:
    resolved_llm = llm or FakeLlmClient(turns=())
    session_service = AssistantSessionService(backend)
    executor = ToolExecutor(registry, max_result_chars=20000)
    applicant = ApplicantAgent(
        backend_client=backend,
        llm_client=resolved_llm,
        session_service=session_service,
        tool_executor=executor,
    )
    runtime = AssistantRuntime(
        llm_client=resolved_llm,
        tool_registry=registry,
        tool_executor=executor,
        tool_policy=ToolPolicy(),
        max_tool_steps=4,
    )
    service = AssistantService(
        backend_client=backend,
        session_service=session_service,
        context_builder=AssistantContextBuilder(),
        agent_router=AgentRouter((applicant,)),
        runtime=runtime,
        max_history_messages=20,
    )
    return ProcurementAssistant(service)


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


@pytest.mark.asyncio
async def test_llm_draft_tool_call_asks_only_next_field() -> None:
    backend = FakeBackendClient(user())
    registry = ToolRegistry()
    registry.register(UpdatePurchaseDraftTool(backend))
    llm = FakeLlmClient(
        turns=(
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
    assistant = _assistant(backend, registry, llm)

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
    assert "设备专业" in response.text
    assert "待补充字段" not in response.text
    assert backend.call_counts["update_applicant_fields"] == 1
    assert len(llm.calls) == 1
    assert llm.tool_choices == ["required"]


@pytest.mark.asyncio
async def test_plain_text_query_response_never_forces_a_draft_write() -> None:
    backend = FakeBackendClient(user())
    registry = ToolRegistry()
    registry.register(QueryPurchaseRequestsTool(backend))
    registry.register(UpdatePurchaseDraftTool(backend))
    llm = FakeLlmClient(turns=())
    assistant = _assistant(backend, registry, llm)

    response = await assistant.handle(
        TextMessageEvent(
            event_id="query-event",
            external_user_id="ou_test",
            external_message_id="query-message",
            chat_id="query-chat",
            text="帮我查一下我之前一共提交了多少采购申请",
        )
    )

    assert isinstance(response, AssistantInteractionResponse)
    assert "共 **0** 条采购申请" in response.view.elements[0].markdown
    assert backend.call_counts["create_requirement"] == 0
    assert backend.call_counts["update_applicant_fields"] == 0
    assert backend.call_counts["list_purchase_records"] == 1
    assert llm.tool_choices == [None]


@pytest.mark.asyncio
async def test_query_blocks_an_unexpected_draft_tool_call() -> None:
    backend = FakeBackendClient(user())
    registry = ToolRegistry()
    registry.register(QueryPurchaseRequestsTool(backend))
    registry.register(UpdatePurchaseDraftTool(backend))
    llm = FakeLlmClient(
        turns=(
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(
                        id="unexpected-write",
                        name="update_purchase_draft",
                        arguments_json='{"device_name":"不应保存"}',
                    ),
                )
            ),
            AssistantTurn(content="查询工具调用失败, 请稍后重试。"),
        )
    )
    assistant = _assistant(backend, registry, llm)

    await assistant.handle(
        TextMessageEvent(
            event_id="blocked-write-event",
            external_user_id="ou_test",
            external_message_id="blocked-write-message",
            chat_id="query-chat",
            text="帮我查看采购申请详情",
        )
    )

    assert backend.call_counts["create_requirement"] == 0
    assert backend.call_counts["update_applicant_fields"] == 0
    assert backend.call_counts["list_purchase_records"] == 0


@pytest.mark.asyncio
async def test_applicant_history_query_returns_a_clickable_card_with_backend_total() -> None:
    backend = FakeBackendClient(user())
    backend.purchase_records.extend(
        (
            PurchaseRecord(
                requirement_id=1,
                requirement_no="PR-1",
                device_name="服务器",
                status=RequirementStatus.PENDING_REVIEW,
                created_at=datetime(2026, 8, 1, tzinfo=UTC),
            ),
            PurchaseRecord(
                requirement_id=2,
                requirement_no="PR-2",
                device_name="交换机",
                status=RequirementStatus.COMPLETED,
                created_at=datetime(2026, 8, 2, tzinfo=UTC),
            ),
        )
    )
    registry = ToolRegistry()
    registry.register(QueryPurchaseRequestsTool(backend))
    registry.register(UpdatePurchaseDraftTool(backend))
    llm = FakeLlmClient(turns=(AssistantTurn(content="您之前共提交了 2 条采购申请, 详情如下。"),))
    assistant = _assistant(backend, registry, llm)

    response = await assistant.handle(
        TextMessageEvent(
            event_id="history-card-event",
            external_user_id="ou_test",
            external_message_id="history-card-message",
            chat_id="history-chat",
            text="帮我查一下我之前一共提交了多少采购申请",
        )
    )

    assert isinstance(response, AssistantInteractionResponse)
    assert response.view.title == "我的采购申请"
    assert "您之前共提交了 2 条采购申请" in response.view.elements[0].markdown
    assert "共 **2** 条采购申请" in response.view.elements[0].markdown
    assert [action.action_id for action in response.view.actions] == [
        "applicant.open",
        "applicant.open",
    ]
    assert backend.call_counts["create_requirement"] == 0
    assert backend.call_counts["update_applicant_fields"] == 0


@pytest.mark.asyncio
async def test_verified_pending_draft_field_reply_retries_the_draft_tool() -> None:
    backend = FakeBackendClient(user())
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_test")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    backend.seed_requirement(
        RequirementDetail(
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
    )
    await backend.update_agent_state(
        identity=identity,
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
    llm = FakeLlmClient(
        turns=(
            AssistantTurn(content="我会记录这个品牌。"),
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(
                        id="brand-call",
                        name="update_purchase_draft",
                        arguments_json='{"brand":"华为"}',
                    ),
                )
            ),
        )
    )
    assistant = _assistant(backend, registry, llm)

    await assistant.handle(
        TextMessageEvent(
            event_id="brand-event",
            external_user_id="ou_test",
            external_message_id="brand-message",
            chat_id="draft-chat",
            text="华为",
        )
    )

    assert backend.call_counts["get_requirement"] >= 1
    assert backend.call_counts["update_applicant_fields"] == 1
    assert llm.tool_choices == [None]


def test_applicant_prompt_history_is_limited_to_the_latest_exchange() -> None:
    backend = FakeBackendClient(user())
    registry = ToolRegistry()
    applicant = ApplicantAgent(
        backend_client=backend,
        llm_client=FakeLlmClient(turns=()),
        session_service=AssistantSessionService(backend),
        tool_executor=ToolExecutor(registry, max_result_chars=20000),
    )
    history = tuple(
        AssistantMessage(role="user", content=f"message-{index}") for index in range(10)
    )

    messages = applicant.build_messages(context=context(), history=history)

    assert [message.content for message in messages[1:]] == ["message-8", "message-9"]


def test_applicant_prompt_is_injected_into_llm_system_context() -> None:
    backend = FakeBackendClient(user())
    applicant = ApplicantAgent(
        backend_client=backend,
        llm_client=FakeLlmClient(turns=()),
        session_service=AssistantSessionService(backend),
        tool_executor=ToolExecutor(ToolRegistry(), max_result_chars=20000),
    )

    messages = applicant.build_messages(
        context=context(), history=(AssistantMessage(role="user", content="我要采购服务器"),)
    )
    payload = OpenAICompatibleLlmClient._message_payload(messages[0])

    assert payload["role"] == "system"
    assert "需求人采购助手" in str(payload["content"])
    assert "update_purchase_draft" in str(payload["content"])


@pytest.mark.asyncio
async def test_session_service_reads_latest_message_page() -> None:
    backend = FakeBackendClient(user())
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_test")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    for index in range(55):
        await backend.append_agent_message(
            identity=identity,
            conversation_id=conversation.conversation_id,
            external_message_id=f"message-{index}",
            sender_type=AgentMessageSender.USER,
            content=f"content-{index}",
        )

    page = await AssistantSessionService(backend).messages(
        identity=identity, conversation_id=conversation.conversation_id
    )

    assert page.page == 2
    assert page.items[-1].external_message_id == "message-54"


def test_explicit_new_draft_discards_old_history_and_requires_start_new() -> None:
    backend = FakeBackendClient(user())
    registry = ToolRegistry()
    applicant = ApplicantAgent(
        backend_client=backend,
        llm_client=FakeLlmClient(turns=()),
        session_service=AssistantSessionService(backend),
        tool_executor=ToolExecutor(registry, max_result_chars=20000),
    )
    history = (
        AssistantMessage(role="assistant", content="申请原因为系统告警"),
        AssistantMessage(role="user", content="电气"),
        AssistantMessage(role="assistant", content="申请原因为系统告警"),
        AssistantMessage(role="user", content="请新建一张采购草稿: 我要购买一块科华的电源整流模块"),
    )

    messages = applicant.build_messages(context=context(), history=history)

    assert "start_new=true" in (messages[1].content or "")
    assert [message.content for message in messages[2:]] == [history[-1].content]
    assert all("系统告警" not in (message.content or "") for message in messages)
    prepared = applicant.prepare_tool_call(
        AssistantToolCall(
            id="new-draft",
            name="update_purchase_draft",
            arguments_json='{"requirement_id":91083,"device_name":"电源整流模块"}',
        ),
        user_text=history[-1].content or "",
    )
    arguments = json.loads(prepared.arguments_json)
    assert arguments["start_new"] is True
    assert "requirement_id" not in arguments


@pytest.mark.parametrize(
    "text",
    [
        "我要购买一块科华的电源整流模块",
        "我想采购两台服务器",
        "帮我买一个交换机",
        "需要采购三台空调",
    ],
)
def test_natural_purchase_request_starts_a_new_draft(text: str) -> None:
    assert ApplicantAgent._explicit_new_draft_text(text)


def test_purchase_query_does_not_start_a_new_draft() -> None:
    assert not ApplicantAgent._explicit_new_draft_text("查询我需要采购的设备列表")


def test_applicant_history_query_extracts_status_time_and_explicit_fields() -> None:
    arguments = ApplicantAgent._history_query_arguments(
        "统计本月待审核采购申请,设备名称是服务器,品牌为戴尔"
    )

    assert arguments == {
        "operation": "SEARCH",
        "result_limit": 10,
        "status": "PENDING_REVIEW",
        "time_expression": "本月",
        "device_name": "服务器",
        "brand": "戴尔",
    }


@pytest.mark.parametrize(
    ("pending_field", "reply", "expected"),
    [
        ("quantity", "需要 3 台", {"quantity": "3"}),
        ("quantity", "三个左右", None),
        ("unit", "按台", {"unit": "台"}),
        ("unit", "每批", None),
        ("brand", "品牌是华为", {"brand": "华为"}),
        ("model", "型号:R760", {"model": "R760"}),
        ("device_profession", "1", {"device_profession": "暖通"}),
        ("device_profession", "选择8", {"device_profession": "其他"}),
    ],
)
def test_pending_field_arguments_are_field_aware(
    pending_field: str, reply: str, expected: dict[str, object] | None
) -> None:
    assert (
        ApplicantAgent._pending_field_arguments(pending_field=pending_field, user_text=reply)
        == expected
    )


@pytest.mark.parametrize("reply", ["算了", "不用了谢谢", "先不填这个", "取消这张草稿"])
def test_cancel_intent_never_allows_draft_write(reply: str) -> None:
    assert ApplicantAgent._is_cancel_intent(reply)
    assert not ApplicantAgent._looks_like_pending_field_reply(pending_field="brand", text=reply)


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
    applicant = ApplicantAgent(
        backend_client=backend,
        llm_client=FakeLlmClient(turns=()),
        session_service=AssistantSessionService(backend),
        tool_executor=ToolExecutor(registry, max_result_chars=20000),
    )
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
    response = await applicant._respond_to_draft_update(
        result=result,
        context=context().model_copy(
            update={
                "conversation_id": conversation.conversation_id,
                "active_requirement_id": 1,
            }
        ),
        external_message_id="m1",
    )
    assert isinstance(response, AssistantTextResponse)
    assert "根据历史采购记录" in response.text
    assert response.text.count("华为") == 1
    assert "1. 华为" in response.text
    assert "2. H3C" in response.text
    assert "3. 锐捷" in response.text
    assert backend.call_counts["recommend_products"] == 1


@pytest.mark.asyncio
async def test_three_turn_llm_draft_flow_returns_confirmation_card() -> None:
    backend = FakeBackendClient(user())
    backend.product_recommendations = ProductRecommendations(
        items=tuple(
            ProductRecommendation(
                brand=brand,
                model=model,
                historical_count=3,
                last_purchased_at=datetime(2026, 8, index, tzinfo=UTC),
            )
            for index, (brand, model) in enumerate(
                (
                    ("维谛", "PEX4"),
                    ("维谛", "Liebert CRV"),
                    ("维谛", "Liebert DSE"),
                    ("施耐德", "Uniflair"),
                    ("艾特网能", "CyberMate"),
                ),
                start=1,
            )
        )
    )
    registry = ToolRegistry()
    registry.register(UpdatePurchaseDraftTool(backend))
    registry.register(RecommendProductOptionsTool(backend))
    llm = FakeLlmClient(
        turns=(
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(
                        id="base-fields",
                        name="update_purchase_draft",
                        arguments_json=(
                            '{"device_profession":"暖通","device_name":"精密空调",'
                            '"quantity":"2","unit":"台",'
                            '"application_reason":"机房制冷扩容"}'
                        ),
                    ),
                )
            ),
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(
                        id="brand-selection",
                        name="update_purchase_draft",
                        arguments_json='{"selection_index":1}',
                    ),
                )
            ),
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(
                        id="model-value",
                        name="update_purchase_draft",
                        arguments_json='{"model":"PEX4"}',
                    ),
                )
            ),
        )
    )
    assistant = _assistant(backend, registry, llm)

    first = await assistant.handle(
        TextMessageEvent(
            event_id="e1",
            external_user_id="ou_test",
            external_message_id="m1",
            chat_id="c1",
            text="帮我采购两台精密空调, 用于机房制冷扩容。",
        )
    )
    second = await assistant.handle(
        TextMessageEvent(
            event_id="e2",
            external_user_id="ou_test",
            external_message_id="m2",
            chat_id="c1",
            text="第一个。",
        )
    )
    third = await assistant.handle(
        TextMessageEvent(
            event_id="e3",
            external_user_id="ou_test",
            external_message_id="m3",
            chat_id="c1",
            text="PEX4。",
        )
    )

    assert isinstance(first, AssistantTextResponse)
    assert "根据历史采购记录" in first.text
    assert isinstance(second, AssistantTextResponse)
    assert "根据历史采购记录" in second.text
    assert isinstance(third, AssistantInteractionResponse)
    conversation = await backend.get_or_create_agent_conversation(
        identity=PlatformIdentity.create(PlatformType.FEISHU, "ou_test"),
        current_action="ASSISTANT_CHAT",
    )
    state = await backend.get_agent_state(
        identity=PlatformIdentity.create(PlatformType.FEISHU, "ou_test"),
        conversation_id=conversation.conversation_id,
    )
    assert state.purchase_request_id is not None
    detail = await backend.get_requirement(
        identity=PlatformIdentity.create(PlatformType.FEISHU, "ou_test"),
        requirement_id=state.purchase_request_id,
    )
    assert detail.applicant_fields == ApplicantFields(
        device_profession="暖通",
        device_name="精密空调",
        brand="维谛",
        model="PEX4",
        quantity="2",
        unit="台",
        application_reason="机房制冷扩容",
    )


def test_device_profession_followup_includes_ranked_history_recommendations() -> None:
    result = UpdatePurchaseDraftResult(
        status="SUCCESS",
        updated_fields=("device_name",),
        updated_values={"device_name": "空调机组"},
        missing_fields=("device_profession",),
        next_missing_field="device_profession",
        device_profession_recommendations=("暖通", "电气"),
    )

    text = ApplicantAgent._draft_followup_text(result, None)

    assert "1、暖通" in text
    assert "2、电气" in text
    assert "推荐优先选择" in text
    assert "请回复序号选择" in text
