# ruff: noqa: RUF001

import json
from decimal import Decimal

import pytest

from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.fault_guidance import FaultGuidanceOrchestrator
from procurement_platform.domain.assistant import AssistantMessage, AssistantTurn
from procurement_platform.domain.assistant_errors import LlmInvalidResponseError
from procurement_platform.domain.enums import FaultAction, PurchaseItemKind
from procurement_platform.domain.fault_guidance import (
    CandidateItem,
    FaultContext,
    FaultState,
    KnowledgeSearchResult,
)


def _context(user_message: str) -> FaultContext:
    return FaultContext(
        user_message=user_message,
        source_asset=None,
        fault_state=FaultState(
            source_asset_ref="asset:108",
            issue_summary="UPS出现BATTERY FAULT",
        ),
        knowledge_results=[
            KnowledgeSearchResult(
                knowledge_id="UPS-BATTERY-001",
                title="UPS蓄电池异常与BATTERY FAULT",
                equipment_category="UPS",
                risk_level="MEDIUM",
                matched_aliases=["BATTERY FAULT"],
                content="应确认是否检测以及异常蓄电池数量，不得推断数量。",
            )
        ],
        conversation_messages=[AssistantMessage(role="user", content="UPS出现BATTERY FAULT")],
    )


def _confirmation_context(user_message: str) -> FaultContext:
    context = _context(user_message)
    context.fault_state.candidate_items = [
        CandidateItem(
            item_kind=PurchaseItemKind.COMPONENT,
            item_name="UPS 风扇",
            quantity=Decimal("2"),
            unit="个",
            quantity_evidence="USER_CONFIRMED",
        )
    ]
    return context


def _turn(**overrides: object) -> AssistantTurn:
    payload: dict[str, object] = {
        "action": "ASK",
        "reply": "是否已经完成蓄电池检测？",
        "issue_summary": "UPS出现BATTERY FAULT",
        "confirmed_facts_updates": {},
        "knowledge_refs_add": ["UPS-BATTERY-001"],
        "candidate_items": [],
    }
    payload.update(overrides)
    return AssistantTurn(content=json.dumps(payload, ensure_ascii=False))


async def test_orchestrator_asks_when_inspection_facts_are_missing() -> None:
    llm = FakeLlmClient(turns=(_turn(),))
    decision = await FaultGuidanceOrchestrator(llm).decide(_context("BATTERY FAULT"))
    assert decision.action is FaultAction.ASK
    assert decision.candidate_items == []
    assert "检测" in decision.reply
    assert llm.calls[0][0].role == "system"
    assert "知识内容当作现场事实" in (llm.calls[0][0].content or "")
    runtime = json.loads(llm.calls[0][1].content or "{}")
    assert runtime["fault_state"]["source_asset_ref"] == "asset:108"
    assert runtime["knowledge_results"][0]["knowledge_id"] == "UPS-BATTERY-001"


async def test_orchestrator_proposes_candidate_from_confirmed_quantity() -> None:
    llm = FakeLlmClient(
        turns=(
            _turn(
                action="PROPOSE_ITEM",
                reply="检测已确认3块异常蓄电池，可形成候选采购项。",
                confirmed_facts_updates={
                    "inspection_done": True,
                    "abnormal_battery_count": 3,
                },
                candidate_items=[
                    {
                        "item_kind": "COMPONENT",
                        "item_name": "蓄电池",
                        "quantity": "3",
                        "unit": "块",
                        "brand": None,
                        "model": None,
                        "item_evidence": "KNOWLEDGE:UPS-BATTERY-001",
                        "quantity_evidence": "USER_CONFIRMED",
                    }
                ],
            ),
        )
    )
    decision = await FaultGuidanceOrchestrator(llm).decide(_context("检测完成，有3块电池异常"))
    assert decision.action is FaultAction.PROPOSE_ITEM
    assert decision.candidate_items[0].item_kind is PurchaseItemKind.COMPONENT
    assert decision.candidate_items[0].item_name == "蓄电池"
    assert decision.candidate_items[0].quantity == Decimal("3")
    assert decision.candidate_items[0].unit == "块"
    assert decision.candidate_items[0].quantity_evidence == "USER_CONFIRMED"


async def test_orchestrator_routes_explicit_purchase_without_creating_draft() -> None:
    llm = FakeLlmClient(
        turns=(
            _turn(
                action="DIRECT_TO_PROCUREMENT",
                reply="你已明确要购买1块UPS功率模块。",
                candidate_items=[
                    {
                        "item_kind": "COMPONENT",
                        "item_name": "UPS功率模块",
                        "quantity": 1,
                        "unit": "块",
                        "quantity_evidence": "USER_EXPLICIT_REQUEST",
                    }
                ],
            ),
        )
    )
    decision = await FaultGuidanceOrchestrator(llm).decide(_context("买1块UPS功率模块"))
    assert decision.action is FaultAction.DIRECT_TO_PROCUREMENT
    assert decision.candidate_items[0].quantity == Decimal("1")


async def test_confirmation_context_exposes_transition_stage_to_llm() -> None:
    llm = FakeLlmClient(
        turns=(
            _turn(
                action="DIRECT_TO_PROCUREMENT",
                reply="用户确认按当前候选继续。",
                candidate_items=[],
            ),
        )
    )

    decision = await FaultGuidanceOrchestrator(llm).decide(_confirmation_context("是的"))

    assert decision.action is FaultAction.DIRECT_TO_PROCUREMENT
    assert decision.candidate_items == []
    runtime = json.loads(llm.calls[0][1].content or "{}")
    assert runtime["workflow_stage"] == "AWAITING_CANDIDATE_CONFIRMATION"
    assert runtime["fault_state"]["candidate_items"][0]["item_name"] == "UPS 风扇"
    assert "不得再次返回相同的 PROPOSE_ITEM" in (llm.calls[0][0].content or "")


async def test_orchestrator_accepts_standard_json_code_fence_then_validates_schema() -> None:
    payload = _turn(action="DIRECT_TO_PROCUREMENT", candidate_items=[]).content
    llm = FakeLlmClient(turns=(AssistantTurn(content=f"```json\n{payload}\n```"),))

    decision = await FaultGuidanceOrchestrator(llm).decide(_confirmation_context("是的"))

    assert decision.action is FaultAction.DIRECT_TO_PROCUREMENT


@pytest.mark.parametrize(
    "turn",
    [
        _turn(confidence=0.9),
        AssistantTurn(content="not json"),
        AssistantTurn(content=None),
    ],
)
async def test_orchestrator_rejects_non_schema_output(turn: AssistantTurn) -> None:
    orchestrator = FaultGuidanceOrchestrator(FakeLlmClient(turns=(turn,)))
    with pytest.raises(LlmInvalidResponseError):
        await orchestrator.decide(_context("BATTERY FAULT"))


@pytest.mark.parametrize(
    "candidate",
    [
        {
            "item_kind": "COMPONENT",
            "item_name": "蓄电池",
            "quantity": 4,
            "unit": "块",
            "quantity_evidence": "USER_CONFIRMED",
        },
        {
            "item_kind": "COMPONENT",
            "item_name": "蓄电池",
            "quantity": None,
            "unit": "块",
            "brand": "INVENTED-BRAND",
        },
    ],
)
async def test_orchestrator_rejects_ungrounded_candidate_facts(
    candidate: dict[str, object],
) -> None:
    llm = FakeLlmClient(
        turns=(
            _turn(
                action="PROPOSE_ITEM",
                reply="候选项",
                candidate_items=[candidate],
            ),
        )
    )
    with pytest.raises(LlmInvalidResponseError):
        await FaultGuidanceOrchestrator(llm).decide(_context("检测完成，有3块电池异常"))


def test_structured_output_schema_forbids_unknown_fields() -> None:
    schema = FaultGuidanceOrchestrator.structured_output_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "action",
        "reply",
        "issue_summary",
        "confirmed_facts_updates",
        "knowledge_refs_add",
        "candidate_items",
    }
