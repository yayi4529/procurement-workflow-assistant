import hashlib
import json
from collections.abc import Awaitable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from fastapi.testclient import TestClient
from pydantic import SecretStr

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.feishu.fake_client import FakeFeishuClient
from procurement_platform.adapters.feishu.webhook_parser import FeishuWebhookParser
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.adapters.persistence.local_conversation_lock import (
    LocalConversationLockManager,
)
from procurement_platform.adapters.persistence.memory_event_dedup_store import (
    MemoryEventDedupStore,
)
from procurement_platform.adapters.skills import MarkdownRoleSkillLoader
from procurement_platform.application.assistant.agent import ProcurementAgent
from procurement_platform.application.assistant.capabilities import CapabilityPolicy
from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.phase_input import ApplicantPhaseInputParser
from procurement_platform.application.assistant.presentation import LegacyToolResultPresenter
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.service import AssistantService
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tools import ToolExecutor
from procurement_platform.application.assistant.workflow_router import LlmWorkflowRouter
from procurement_platform.application.assistant.workflow_state import WorkflowStateService
from procurement_platform.application.inbound.message_handler import BaseMessageHandler
from procurement_platform.bootstrap.container import (
    ApplicationContainer,
    _build_capability_registry,
)
from procurement_platform.bootstrap.settings import FeishuSettings, Settings
from procurement_platform.domain.assistant import AssistantToolCall, AssistantTurn
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import ProductRecommendation, ProductRecommendations
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole
from procurement_platform.interfaces.http.app import create_app


def test_signed_webhook_runs_strict_skill_and_deduplicates() -> None:
    client, channel, backend, _ = _app()
    payload = _payload("TEST-SKILL-E2E-product-1", "推荐控制电源品牌型号")
    body = json.dumps(payload, ensure_ascii=False).encode()
    timestamp, nonce = "1787500000", "skill-e2e-nonce"
    signature = hashlib.sha256(
        timestamp.encode() + nonce.encode() + b"skill-e2e-encrypt" + body
    ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": signature,
    }

    with client:
        first = client.post("/webhooks/feishu", content=body, headers=headers)
        duplicate = client.post("/webhooks/feishu", content=body, headers=headers)

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert len(channel.reply_interaction_calls) == 1
    recommendation_text = channel.reply_interaction_calls[0][1].elements[0].markdown
    assert "请选择下列品牌或型号的序号" in recommendation_text
    assert "1、TEST-品牌" in recommendation_text
    assert "TEST-型号" in recommendation_text
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_skill_e2e")
    conversation = _run(
        backend.get_or_create_agent_conversation(identity=identity, current_action="ASSISTANT_CHAT")
    )
    state = _run(
        backend.get_agent_state(identity=identity, conversation_id=conversation.conversation_id)
    )
    workflow = WorkflowStateService.from_session(state)
    assert workflow is not None
    assert workflow.workflow_name == "product-recommendation"
    assert workflow.phase in {"retrieve-candidates", "await-selection"}


def test_invalid_signature_is_rejected_without_llm_or_reply() -> None:
    client, channel, _, llm = _app()
    body = json.dumps(_payload("TEST-SKILL-E2E-invalid", "推荐控制电源品牌型号")).encode()

    with client:
        response = client.post(
            "/webhooks/feishu",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Lark-Request-Timestamp": "1787500000",
                "X-Lark-Request-Nonce": "invalid",
                "X-Lark-Signature": "invalid",
            },
        )

    assert response.status_code == 400
    assert not channel.reply_interaction_calls
    assert not llm.calls


def test_candidate_selection_recovers_after_container_rebuild_without_llm() -> None:
    first_client, _, backend, _ = _app()
    first_payload = _signed_request(
        "TEST-SKILL-E2E-recovery-1", "om_skill_recovery_1", "推荐控制电源品牌型号"
    )
    with first_client:
        first = first_client.post("/webhooks/feishu", **first_payload)
    assert first.status_code == 200

    second_client, _, _, second_llm = _app(
        backend=backend,
        turns=(AssistantTurn(content="不应调用"),),
    )
    second_payload = _signed_request("TEST-SKILL-E2E-recovery-2", "om_skill_recovery_2", "第一个")
    with second_client:
        second = second_client.post("/webhooks/feishu", **second_payload)
    assert second.status_code == 200
    assert not second_llm.calls

    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_skill_e2e")
    conversation = _run(
        backend.get_or_create_agent_conversation(identity=identity, current_action="ASSISTANT_CHAT")
    )
    state = _run(
        backend.get_agent_state(identity=identity, conversation_id=conversation.conversation_id)
    )
    workflow = WorkflowStateService.from_session(state)
    assert workflow is not None
    assert workflow.workflow_name == "product-recommendation"
    assert workflow.status.value == "COMPLETED"
    assert workflow.collected_inputs["candidate_reference"] == "legacy-product:1"


def test_candidate_with_quantity_creates_one_draft_and_awaits_card() -> None:
    turns = (
        *_recommendation_turns(),
        AssistantTurn(
            tool_calls=(
                AssistantToolCall(
                    id="draft",
                    name="update_multi_item_draft",
                    arguments_json=(
                        '{"start_new":true,"operation":"REPLACE","items":['
                        '{"item_kind":"EQUIPMENT","item_name":"控制电源",'
                        '"quantity":"2","brand":"TEST-品牌",'
                        '"model":"TEST-型号"}],"application_reason":"补充库存"}'
                    ),
                ),
            )
        ),
        AssistantTurn(content="草稿已保存,请在正式卡片中确认。"),
    )
    client, channel, backend, llm = _app(turns=turns)
    first = _signed_request("TEST-SKILL-E2E-draft-1", "om_skill_draft_1", "推荐控制电源品牌型号")
    second = _signed_request(
        "TEST-SKILL-E2E-draft-2", "om_skill_draft_2", "用第一个创建草稿,数量2个"
    )
    third = _signed_request("TEST-SKILL-E2E-draft-3", "om_skill_draft_3", "申请原因是补充库存")
    with client:
        assert client.post("/webhooks/feishu", **first).status_code == 200
        assert client.post("/webhooks/feishu", **second).status_code == 200
        assert client.post("/webhooks/feishu", **third).status_code == 200

    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_skill_e2e")
    conversation = _run(
        backend.get_or_create_agent_conversation(identity=identity, current_action="ASSISTANT_CHAT")
    )
    state = _run(
        backend.get_agent_state(identity=identity, conversation_id=conversation.conversation_id)
    )
    workflow = WorkflowStateService.from_session(state)
    assert workflow is not None
    assert workflow.workflow_name == "create-draft"
    assert workflow.status.value == "AWAITING_CARD"
    assert backend.call_counts["replace_request_items"] == 1
    detail_card = next(
        view for _, view in channel.reply_interaction_calls if len(view.elements) > 1
    )
    assert {action.action_id for action in detail_card.actions} == {
        "applicant.prepare_submit",
        "applicant.list",
    }
    assert len(llm.calls) == 3


def test_purchase_name_automatically_recommends_historical_brand_and_model() -> None:
    turns = (
        AssistantTurn(
            content=(
                '{"action":"START","workflow_name":"create-draft",'
                '"confidence":"HIGH","reason_code":"PURCHASE_REQUEST"}'
            )
        ),
        AssistantTurn(
            tool_calls=(
                AssistantToolCall(
                    id="recommend-history",
                    name="recommend_products_by_name",
                    arguments_json='{"device_name":"控制电源","top_k":5}',
                ),
            )
        ),
        AssistantTurn(content="历史采购过 TEST-品牌 TEST-型号,请选候选。"),
    )
    client, channel, backend, _ = _app(turns=turns)

    with client:
        response = client.post(
            "/webhooks/feishu",
            **_signed_request("TEST-AUTO-RECOMMEND-1", "om_auto_recommend_1", "我要买2个控制电源"),
        )

    assert response.status_code == 200
    assert backend.call_counts["recommend_products"] == 1
    assert backend.call_counts["replace_request_items"] == 0
    assert "TEST-品牌" in channel.reply_interaction_calls[-1][1].elements[0].markdown
    workflow = _workflow(backend)
    assert workflow.workflow_name == "create-draft"
    assert workflow.phase == "await-selection"
    assert workflow.status.value == "AWAITING_USER"


def test_purchase_name_without_history_skips_recommendation_and_creates_draft() -> None:
    turns = (
        AssistantTurn(
            content=(
                '{"action":"START","workflow_name":"create-draft",'
                '"confidence":"HIGH","reason_code":"PURCHASE_REQUEST"}'
            )
        ),
        AssistantTurn(
            tool_calls=(
                AssistantToolCall(
                    id="recommend-history-empty",
                    name="recommend_products_by_name",
                    arguments_json='{"device_name":"新商品","top_k":5}',
                ),
            )
        ),
        AssistantTurn(content="没有历史品牌型号。"),
        AssistantTurn(
            tool_calls=(
                AssistantToolCall(
                    id="draft-without-recommendation",
                    name="update_multi_item_draft",
                    arguments_json=(
                        '{"start_new":true,"operation":"REPLACE","items":['
                        '{"item_kind":"EQUIPMENT","item_name":"新商品","quantity":"2"}],'
                        '"application_reason":"补充库存"}'
                    ),
                ),
            )
        ),
        AssistantTurn(content="草稿已保存,请在正式卡片中确认。"),
    )
    backend = FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="Skill E2E",
            mobile=None,
            status="ACTIVE",
            roles=(UserRole(role_code=RoleCode.APPLICANT),),
            buildings=(UserBuilding(building_id=1, building_name="TEST-楼", is_primary=True),),
        )
    )
    client, _, backend, _ = _app(backend=backend, turns=turns)

    with client:
        first_response = client.post(
            "/webhooks/feishu",
            **_signed_request(
                "TEST-AUTO-RECOMMEND-EMPTY", "om_auto_recommend_empty", "我要买2个新商品"
            ),
        )
        response = client.post(
            "/webhooks/feishu",
            **_signed_request(
                "TEST-AUTO-RECOMMEND-EMPTY-REASON",
                "om_auto_recommend_empty_reason",
                "申请原因是补充库存",
            ),
        )

    assert first_response.status_code == 200
    assert response.status_code == 200
    assert backend.call_counts["recommend_products"] == 1
    assert backend.call_counts["replace_request_items"] == 1
    workflow = _workflow(backend)
    assert workflow.status.value == "AWAITING_CARD"


def _workflow(backend: FakeBackendClient):
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_skill_e2e")
    conversation = _run(
        backend.get_or_create_agent_conversation(identity=identity, current_action="ASSISTANT_CHAT")
    )
    state = _run(
        backend.get_agent_state(identity=identity, conversation_id=conversation.conversation_id)
    )
    workflow = WorkflowStateService.from_session(state)
    assert workflow is not None
    return workflow


def _app(
    *,
    backend: FakeBackendClient | None = None,
    turns: tuple[AssistantTurn, ...] | None = None,
) -> tuple[TestClient, FakeFeishuClient, FakeBackendClient, FakeLlmClient]:
    settings = Settings(
        environment="test",
        service_name="skill-e2e",
        backend_base_url="http://backend",
        backend_request_timeout_seconds=1,
        identity_gateway_secret=SecretStr("identity"),
        llm_enabled=True,
        llm_api_key=SecretStr("fake"),
        llm_model="fake",
        llm_skill_routing_mode="strict",
        feishu=FeishuSettings(
            enabled=True,
            app_id="app",
            app_secret=SecretStr("secret"),
            verification_token=SecretStr("verify"),
            encrypt_key=SecretStr("skill-e2e-encrypt"),
        ),
    )
    if backend is None:
        backend = FakeBackendClient(
            CurrentUser(
                employee_id=1,
                name="Skill E2E",
                mobile=None,
                status="ACTIVE",
                roles=(UserRole(role_code=RoleCode.APPLICANT),),
                buildings=(UserBuilding(building_id=1, building_name="TEST-楼", is_primary=True),),
            )
        )
        backend.product_recommendations = ProductRecommendations(
            items=(
                ProductRecommendation(
                    product_id=1,
                    brand="TEST-品牌",
                    model="TEST-型号",
                    historical_count=2,
                    last_purchased_at=datetime(2026, 8, 1, tzinfo=UTC),
                ),
            )
        )
    llm = FakeLlmClient(turns=turns or _recommendation_turns())
    registry = _build_capability_registry(backend, llm)
    sessions = AssistantSessionService(backend)
    skills = (
        MarkdownRoleSkillLoader(Path(__file__).parents[2] / "skills")
        .load()
        .validate_capabilities(registry.tool_registry.registered_names)
    )
    agent = ProcurementAgent(
        runtime=AssistantRuntime(
            llm_client=llm,
            tool_registry=registry.tool_registry,
            tool_executor=ToolExecutor(registry.tool_registry, max_result_chars=10_000),
            max_tool_steps=4,
        ),
        capability_policy=CapabilityPolicy(registry),
        session_service=sessions,
        result_presenter=LegacyToolResultPresenter(
            backend_client=backend, session_service=sessions
        ),
        role_skill_registry=skills,
        workflow_router=LlmWorkflowRouter(llm),
        workflow_state_service=WorkflowStateService(backend),
        phase_input_parser=ApplicantPhaseInputParser(llm),
        skill_routing_mode="strict",
    )
    service = AssistantService(
        backend_client=backend,
        session_service=sessions,
        context_builder=AssistantContextBuilder(),
        procurement_agent=agent,
        max_history_messages=20,
    )
    channel = FakeFeishuClient()
    container = ApplicationContainer(
        settings=settings,
        backend_client=backend,
        channel_client=channel,
        webhook_parser=FeishuWebhookParser(
            verification_token="verify", encrypt_key="skill-e2e-encrypt"
        ),
        event_dedup_store=MemoryEventDedupStore(),
        message_handler=BaseMessageHandler(
            channel,
            backend_client=backend,
            assistant_service=service,
            conversation_lock_manager=LocalConversationLockManager(),
        ),
    )
    return TestClient(create_app(settings, container)), channel, backend, llm


def _payload(event_id: str, text: str, message_id: str = "om_skill_e2e") -> dict[str, object]:
    return {
        "header": {
            "token": "verify",
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
        },
        "event": {
            "sender": {"sender_id": {"open_id": "ou_skill_e2e"}},
            "message": {
                "message_id": message_id,
                "message_type": "text",
                "chat_type": "p2p",
                "chat_id": "oc_skill_e2e",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        },
    }


def _signed_request(event_id: str, message_id: str, text: str) -> dict[str, object]:
    body = json.dumps(_payload(event_id, text, message_id), ensure_ascii=False).encode()
    timestamp, nonce = "1787500000", f"nonce-{event_id}"
    signature = hashlib.sha256(
        timestamp.encode() + nonce.encode() + b"skill-e2e-encrypt" + body
    ).hexdigest()
    return {
        "content": body,
        "headers": {
            "Content-Type": "application/json",
            "X-Lark-Request-Timestamp": timestamp,
            "X-Lark-Request-Nonce": nonce,
            "X-Lark-Signature": signature,
        },
    }


def _recommendation_turns() -> tuple[AssistantTurn, ...]:
    return (
        AssistantTurn(
            content=(
                '{"action":"START","workflow_name":"product-recommendation",'
                '"confidence":"HIGH","reason_code":"PRODUCT_REQUEST"}'
            )
        ),
        AssistantTurn(
            tool_calls=(
                AssistantToolCall(
                    id="recommend",
                    name="recommend_products_by_name",
                    arguments_json='{"device_name":"控制电源","top_k":5}',
                ),
            )
        ),
    )


ResultT = TypeVar("ResultT")


def _run(coroutine: Awaitable[ResultT]) -> ResultT:
    import asyncio

    return asyncio.run(coroutine)
