from pathlib import Path

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.skills import MarkdownRoleSkillLoader
from procurement_platform.application.assistant.capabilities.assets import (
    AssetFact,
    ResolveAssetResult,
)
from procurement_platform.application.assistant.capabilities.intelligence import (
    FindSimilarPurchasesResult,
    SimilarPurchaseCandidate,
)
from procurement_platform.application.assistant.evidence import (
    EvidenceReferenceExtractorRegistry,
)
from procurement_platform.application.assistant.hybrid_routing import (
    HybridDifferenceType,
    HybridRouteComparison,
)
from procurement_platform.application.assistant.phase_input import (
    ApplicantPhaseInputParser,
    PhaseParseResult,
)
from procurement_platform.application.assistant.workflow_execution import TurnExecutionBudget
from procurement_platform.application.assistant.workflow_router import (
    LlmWorkflowRouter,
    WorkflowRouteAction,
)
from procurement_platform.application.assistant.workflow_state import (
    WorkflowRunState,
    WorkflowStateService,
    WorkflowStatus,
)
from procurement_platform.application.assistant.workflow_transition import (
    WorkflowTransitionEvent,
    WorkflowTransitionService,
)
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantToolDefinition,
    AssistantTurn,
)
from procurement_platform.domain.assistant_session import AgentSessionState, AgentSessionStateUpdate
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.user import CurrentUser, UserRole


class RouterLlm:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    async def complete(
        self,
        *,
        messages: tuple[AssistantMessage, ...],
        tools: tuple[AssistantToolDefinition, ...],
        tool_choice: str | None = None,
    ) -> AssistantTurn:
        del messages, tools, tool_choice
        self.calls += 1
        return AssistantTurn(content=self.content)


def _skill(role: RoleCode):
    registry = MarkdownRoleSkillLoader(Path(__file__).parents[2] / "skills").load()
    skill = registry.get(role)
    assert skill is not None
    return skill


@pytest.mark.asyncio
async def test_router_uses_structured_output_for_new_goal() -> None:
    llm = RouterLlm(
        '{"action":"START","workflow_name":"procurement-analytics",'
        '"confidence":"HIGH","reason_code":"ANALYTICS_REQUEST"}'
    )
    route = await LlmWorkflowRouter(llm).route(
        user_text="统计今年每月采购金额",
        role=RoleCode.PURCHASER,
        skill=_skill(RoleCode.PURCHASER),
        current=None,
    )

    assert route.action is WorkflowRouteAction.START
    assert route.workflow_name == "procurement-analytics"
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_router_continues_parseable_pending_reply_without_llm() -> None:
    llm = RouterLlm("invalid")
    current = WorkflowRunState(
        role=RoleCode.APPLICANT,
        skill_name="applicant",
        workflow_name="fault-procurement",
        phase="confirm-items",
        status=WorkflowStatus.AWAITING_USER,
    )
    route = await LlmWorkflowRouter(llm).route(
        user_text="2个风扇、4个电容",
        role=RoleCode.APPLICANT,
        skill=_skill(RoleCode.APPLICANT),
        current=current,
    )

    assert route.action is WorkflowRouteAction.CONTINUE
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_workflow_state_merge_preserves_other_collected_data() -> None:
    user = CurrentUser(
        employee_id=1,
        name="Purchaser",
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=RoleCode.PURCHASER),),
        buildings=(),
    )
    backend = FakeBackendClient(user)
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_workflow_state")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    await backend.update_agent_state(
        identity=identity,
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(collected_data={"task_v2:name": "开关电源"}),
    )
    service = WorkflowStateService(backend)
    workflow = WorkflowRunState(
        role=RoleCode.PURCHASER,
        skill_name="purchaser",
        workflow_name="procurement-analytics",
        phase="execute",
    )

    await service.save(
        identity=identity,
        conversation_id=conversation.conversation_id,
        session=None,
        workflow=workflow,
    )
    saved = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )

    assert saved.collected_data["task_v2:name"] == "开关电源"
    assert WorkflowStateService.from_session(saved) == workflow


@pytest.mark.asyncio
async def test_phase_parser_extracts_multiple_confirmed_items_without_llm() -> None:
    llm = RouterLlm("invalid")
    parsed = await ApplicantPhaseInputParser(llm).parse(
        parser_name="applicant-confirmed-items",
        user_text="2个风扇、4个电容都确认损坏",
        allowed_intents=("CONFIRM_ITEMS",),
    )

    assert parsed.result is PhaseParseResult.MATCH
    assert parsed.intent == "CONFIRM_ITEMS"
    assert '"quantity": 2' in str(parsed.collected_inputs["items_json"])
    assert '"quantity": 4' in str(parsed.collected_inputs["items_json"])
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_phase_parser_extracts_inline_quantity_after_purchase_verb() -> None:
    parsed = await ApplicantPhaseInputParser(RouterLlm("invalid")).parse(
        parser_name="applicant-items",
        user_text="我要买1个开关电源",
        allowed_intents=("SAVE_ITEMS",),
    )

    assert parsed.result is PhaseParseResult.MATCH
    assert '"item_name": "开关电源"' in str(parsed.collected_inputs["items_json"])
    assert '"quantity": 1' in str(parsed.collected_inputs["items_json"])


@pytest.mark.asyncio
async def test_phase_parser_detects_new_purchase_before_pending_continuation() -> None:
    llm = RouterLlm("invalid")
    parsed = await ApplicantPhaseInputParser(llm).parse(
        parser_name="applicant-candidate-selection",
        user_text="我要买2个开关电源",
        allowed_intents=("SELECT_ONLY", "SELECT_AND_DRAFT", "CANCEL"),
    )

    assert parsed.result is PhaseParseResult.NEW_GOAL
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_application_reason_keeps_fault_replacement_as_current_field() -> None:
    llm = RouterLlm("invalid")
    parsed = await ApplicantPhaseInputParser(llm).parse(
        parser_name="applicant-application-reason",
        user_text="机房UPS故障更换",
        allowed_intents=("SAVE_APPLICATION_REASON",),
    )

    assert parsed.result is PhaseParseResult.MATCH
    assert parsed.collected_inputs == {"application_reason": "机房UPS故障更换"}
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_application_reason_allows_explicit_new_purchase() -> None:
    parsed = await ApplicantPhaseInputParser(RouterLlm("invalid")).parse(
        parser_name="applicant-application-reason",
        user_text="我要买2个服务器电源",
        allowed_intents=("SAVE_APPLICATION_REASON",),
    )

    assert parsed.result is PhaseParseResult.NEW_GOAL


@pytest.mark.asyncio
async def test_phase_parser_keeps_selection_readonly_without_draft_words() -> None:
    llm = RouterLlm("invalid")
    parsed = await ApplicantPhaseInputParser(llm).parse(
        parser_name="applicant-candidate-selection",
        user_text="第一个",
        allowed_intents=("SELECT_ONLY", "SELECT_AND_DRAFT", "CANCEL"),
    )

    assert parsed.result is PhaseParseResult.MATCH
    assert parsed.intent == "SELECT_ONLY"
    assert parsed.collected_inputs == {"candidate_index": 1}
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_phase_parser_extracts_candidate_draft_quantity_without_llm() -> None:
    llm = RouterLlm("invalid")
    parsed = await ApplicantPhaseInputParser(llm).parse(
        parser_name="applicant-candidate-selection",
        user_text="用第一个创建草稿,数量2个",
        allowed_intents=("SELECT_ONLY", "SELECT_AND_DRAFT", "CANCEL"),
    )

    assert parsed.result is PhaseParseResult.MATCH
    assert parsed.intent == "SELECT_AND_DRAFT"
    assert parsed.collected_inputs == {"candidate_index": 1, "candidate_quantity": 2}
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_phase_parser_accepts_quantity_only_for_selected_candidate() -> None:
    parsed = await ApplicantPhaseInputParser(RouterLlm("invalid")).parse(
        parser_name="applicant-items",
        user_text="数量2个",
        allowed_intents=("SAVE_ITEMS",),
    )

    assert parsed.result is PhaseParseResult.MATCH
    assert parsed.collected_inputs == {"candidate_quantity": 2}


@pytest.mark.asyncio
async def test_phase_parser_invalid_llm_output_is_ambiguous() -> None:
    parsed = await ApplicantPhaseInputParser(RouterLlm("not-json")).parse(
        parser_name="applicant-candidate-selection",
        user_text="我觉得上面的可能可以",
        allowed_intents=("SELECT_ONLY", "SELECT_AND_DRAFT", "CANCEL"),
    )

    assert parsed.result is PhaseParseResult.AMBIGUOUS
    assert parsed.reason_code == "LLM_PHASE_PARSE_INVALID"


def test_hybrid_route_comparison_classifies_mismatch() -> None:
    comparison = HybridRouteComparison.compare(
        structured_workflow="fault-procurement", legacy_workflow="create-draft"
    )

    assert not comparison.matched
    assert comparison.difference_type is HybridDifferenceType.WORKFLOW_MISMATCH


def test_v1_workflow_state_migrates_to_explicit_initial_phase() -> None:
    state = AgentSessionState(
        conversation_id=1,
        collected_data={
            WorkflowStateService.encoded_key(): WorkflowRunState(
                role=RoleCode.APPLICANT,
                skill_name="applicant",
                workflow_name="create-draft",
                phase="execute",
            )
            .model_copy(update={"schema_version": 1})
            .model_dump_json()
        },
    )

    migrated = WorkflowStateService.from_session(state)

    assert migrated is not None
    assert migrated.schema_version == 3
    assert migrated.phase == "collect-items"


def test_transition_uses_target_phase_terminal_status() -> None:
    workflow = _skill(RoleCode.APPLICANT).workflows["create-draft"]
    state = WorkflowRunState(
        role=RoleCode.APPLICANT,
        skill_name="applicant",
        workflow_name="create-draft",
        phase="save-draft",
    )

    result = WorkflowTransitionService().transition(
        state=state,
        workflow=workflow,
        event=WorkflowTransitionEvent.CAPABILITY_SUCCESS,
        evidence_refs=("purchase-request:1",),
    )

    assert result.state is not None
    assert result.state.phase == "awaiting-card"
    assert result.state.status is WorkflowStatus.AWAITING_CARD
    assert result.state.evidence_refs == ("purchase-request:1",)


def test_transition_failure_obeys_on_failure() -> None:
    workflow = _skill(RoleCode.APPLICANT).workflows["fault-procurement"]
    state = WorkflowRunState(
        role=RoleCode.APPLICANT,
        skill_name="applicant",
        workflow_name="fault-procurement",
        phase="propose-parts",
    )

    result = WorkflowTransitionService().transition(
        state=state,
        workflow=workflow,
        event=WorkflowTransitionEvent.CAPABILITY_FAILURE,
        error_code="NOT_FOUND",
    )

    assert result.state is not None
    assert result.state.phase == "confirm-replacements"
    assert result.state.status is WorkflowStatus.AWAITING_USER


def test_transition_card_completion_sets_real_terminal_state() -> None:
    workflow = _skill(RoleCode.APPLICANT).workflows["create-draft"]
    state = WorkflowRunState(
        role=RoleCode.APPLICANT,
        skill_name="applicant",
        workflow_name="create-draft",
        phase="awaiting-card",
        status=WorkflowStatus.AWAITING_CARD,
    )

    result = WorkflowTransitionService().transition(
        state=state,
        workflow=workflow,
        event=WorkflowTransitionEvent.CARD_COMPLETED,
    )

    assert result.state is not None
    assert result.state.status is WorkflowStatus.COMPLETED
    assert result.state.terminal_reason == "FORMAL_CARD_COMPLETED"


def test_transition_switches_candidate_to_create_draft_without_losing_evidence() -> None:
    applicant = _skill(RoleCode.APPLICANT)
    state = WorkflowRunState(
        role=RoleCode.APPLICANT,
        skill_name="applicant",
        workflow_name="product-recommendation",
        phase="await-selection",
        status=WorkflowStatus.AWAITING_USER,
        evidence_refs=("recommendation:rec-1",),
    )

    result = WorkflowTransitionService().switch_workflow(
        state=state,
        target_workflow=applicant.workflows["create-draft"],
        target_phase="collect-items",
        collected_inputs={"candidate_reference": "legacy-product:1"},
        status=WorkflowStatus.AWAITING_USER,
    )

    assert result.state is not None
    assert result.state.workflow_name == "create-draft"
    assert result.state.phase == "collect-items"
    assert result.state.evidence_refs == ("recommendation:rec-1",)


def test_turn_budget_hard_stops_after_three_phases() -> None:
    budget = TurnExecutionBudget(max_phase_steps=3)

    assert [budget.begin_phase() for _ in range(4)] == [True, True, True, False]
    assert budget.phase_steps == 3


def test_evidence_registry_extracts_only_stable_explicit_asset_refs() -> None:
    result = ResolveAssetResult(
        status="SUCCESS",
        resolution="RESOLVED",
        asset=AssetFact(
            asset_ref="asset:12",
            asset_code="UPS-02",
            asset_name="2号UPS",
            category_code="UPS",
            category_name="UPS",
            model_ref="model:34",
            building_id=1,
            building_name="测试楼",
            location=None,
            status="ACTIVE",
            criticality="HIGH",
        ),
    )

    refs = EvidenceReferenceExtractorRegistry().extract(
        capability_name="resolve_asset", result=result
    )

    assert refs == ("asset:12", "catalog-model:34")


def test_evidence_registry_extracts_history_number_without_candidate_payload() -> None:
    result = FindSimilarPurchasesResult(
        status="SUCCESS",
        candidates=(
            SimilarPurchaseCandidate(
                candidate_ref="purchase:8",
                requirement_id=8,
                requirement_no="PR-TEST-008",
                similarity_score=0.8,
                match_reasons=("设备名称匹配",),
            ),
        ),
    )

    refs = EvidenceReferenceExtractorRegistry().extract(
        capability_name="find_similar_purchases", result=result
    )

    assert refs == ("history:PR-TEST-008",)
