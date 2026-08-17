import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.assistant.agent import ProcurementAgent
from procurement_platform.application.assistant.capabilities import CapabilityPolicy
from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.presentation import LegacyToolResultPresenter
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.service import AssistantService
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tools import ToolExecutor
from procurement_platform.bootstrap.container import _build_capability_registry
from procurement_platform.domain.assistant import (
    AssistantTextResponse,
    AssistantToolCall,
    AssistantTurn,
)
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.errors import SessionNotFoundError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.user import CurrentUser, UserRole


@pytest.mark.asyncio
async def test_two_multi_role_turns_use_one_agent_without_role_switching() -> None:
    user = CurrentUser(
        employee_id=1,
        name="Multi-role",
        mobile=None,
        status="ACTIVE",
        roles=(
            UserRole(role_code=RoleCode.APPLICANT),
            UserRole(role_code=RoleCode.BUILDING_MANAGER),
        ),
        buildings=(),
    )
    backend = FakeBackendClient(user)
    sessions = AssistantSessionService(backend)
    registry = _build_capability_registry(backend)
    policy = CapabilityPolicy(registry)
    llm = FakeLlmClient(
        turns=(
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(
                        id="pending-query",
                        name="search_purchase_requests",
                        arguments_json='{"result_limit":10}',
                    ),
                )
            ),
            AssistantTurn(content="已查询待审核采购单"),
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(
                        id="created-query",
                        name="search_purchase_requests",
                        arguments_json='{"result_limit":10}',
                    ),
                )
            ),
            AssistantTurn(content="已查询您最近申请的采购单"),
        )
    )
    runtime = AssistantRuntime(
        llm_client=llm,
        tool_registry=registry.tool_registry,
        tool_executor=ToolExecutor(registry.tool_registry, max_result_chars=10_000),
        max_tool_steps=2,
    )
    agent = ProcurementAgent(
        runtime=runtime,
        capability_policy=policy,
        session_service=sessions,
        result_presenter=LegacyToolResultPresenter(
            backend_client=backend,
            session_service=sessions,
        ),
    )
    service = AssistantService(
        backend_client=backend,
        session_service=sessions,
        context_builder=AssistantContextBuilder(),
        procurement_agent=agent,
        max_history_messages=20,
    )

    first = await service.handle(_event("m1", "看看有哪些等我审核的单子"))
    second = await service.handle(_event("m2", "再看看我自己最近申请的采购单"))

    assert first == AssistantTextResponse(text="已查询待审核采购单")
    assert second == AssistantTextResponse(text="已查询您最近申请的采购单")
    assert len(llm.calls) == 4
    assert not hasattr(service, "_agent_router")
    assert not hasattr(service, "_role_intent_resolver")
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_multi")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    with pytest.raises(SessionNotFoundError):
        await backend.get_agent_state(
            identity=identity, conversation_id=conversation.conversation_id
        )
    assert policy.allowed_names_for(user) == frozenset(
        {
            "search_purchase_requests",
            "get_purchase_request",
            "get_purchase_timeline",
            "recommend_products",
            "update_applicant_draft",
            "get_supplier_profile",
            "recommend_suppliers",
            "update_review_draft",
            "diagnose_procurement_need",
            "find_similar_purchases",
            "compare_products",
            "compare_suppliers",
            "search_assets",
            "resolve_asset",
            "get_asset",
            "get_asset_components",
            "get_asset_relations",
        }
    )


def _event(identifier: str, text: str) -> TextMessageEvent:
    return TextMessageEvent(
        event_id=f"event-{identifier}",
        external_user_id="ou_multi",
        external_message_id=identifier,
        chat_id="oc_multi",
        text=text,
    )
