# ruff: noqa: RUF001

from collections import deque
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.knowledge import MarkdownKnowledgeLoader
from procurement_platform.application.fault_guidance import (
    FaultDraftValidator,
    FaultGuidanceService,
    FaultKnowledgeRepository,
    MarkdownKnowledgeSearch,
    ProcurementDraftService,
)
from procurement_platform.application.fault_guidance.service import AssetResolution
from procurement_platform.domain.assets import (
    AssetSummary,
    BuildingSummary,
    EquipmentCategorySummary,
)
from procurement_platform.domain.assistant import AssistantMessage
from procurement_platform.domain.enums import (
    FaultAction,
    PlatformType,
    PurchaseItemKind,
    RoleCode,
)
from procurement_platform.domain.fault_guidance import (
    CandidateItem,
    FaultContext,
    FaultDecision,
    FaultDraftCandidate,
    FaultGuidanceResponse,
    FaultState,
    ProcurementDraftResult,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def _asset(asset_id: int, name: str) -> AssetSummary:
    category = EquipmentCategorySummary(
        category_id=10,
        parent_category_id=None,
        category_code="UPS",
        category_name="UPS",
        category_level=1,
        description=None,
        sort_order=1,
        status="ACTIVE",
    )
    return AssetSummary(
        asset_id=asset_id,
        asset_code=f"TEST-UPS-{asset_id}",
        asset_name=name,
        category_id=10,
        model_id=None,
        building_id=1,
        location="UPS室",
        serial_number=None,
        status="ACTIVE",
        criticality="CRITICAL",
        commissioned_at=date(2025, 1, 1),
        warranty_end_at=None,
        configuration=None,
        aliases=(name,),
        redundancy_group=None,
        redundancy_mode=None,
        remark=None,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        category=category,
        model=None,
        building=BuildingSummary(building_id=1, building_name="一号楼"),
    )


class MemoryFaultStateRepository:
    def __init__(self) -> None:
        self.states: dict[str, FaultState] = {}
        self.events: list[str] = []

    async def get(self, conversation_id: int | str) -> FaultState | None:
        return self.states.get(str(conversation_id))

    async def save(self, conversation_id: int | str, state: FaultState) -> None:
        self.states[str(conversation_id)] = state
        self.events.append("save")

    async def delete(self, conversation_id: int | str) -> None:
        self.states.pop(str(conversation_id), None)
        self.events.append("delete")

    async def reset(self, conversation_id: int | str) -> None:
        self.states.pop(str(conversation_id), None)
        self.events.append("reset")


class ScriptedOrchestrator:
    def __init__(self, *decisions: FaultDecision) -> None:
        self.decisions = deque(decisions)
        self.contexts: list[FaultContext] = []

    async def decide(self, context: FaultContext) -> FaultDecision:
        self.contexts.append(context)
        return self.decisions.popleft()


class AssetProvider:
    def __init__(self) -> None:
        self.assets = {
            "2号UPS": _asset(108, "2号UPS"),
            "3号UPS": _asset(205, "3号UPS"),
        }

    async def resolve(
        self,
        *,
        identity: PlatformIdentity,
        user_message: str,
        current_asset_ref: str | None,
    ) -> AssetResolution:
        del identity
        for phrase, asset in self.assets.items():
            if phrase in user_message:
                return AssetResolution(asset=asset, identified_in_message=True)
        if current_asset_ref is None:
            return AssetResolution(asset=None)
        asset_id = int(current_asset_ref.partition(":")[2])
        return AssetResolution(
            asset=next(item for item in self.assets.values() if item.asset_id == asset_id)
        )


class EmptyHistory:
    async def recent(
        self, *, identity: PlatformIdentity, conversation_id: int
    ) -> list[AssistantMessage]:
        del identity, conversation_id
        return []


class RecordingDraftService:
    def __init__(self, *, fail: bool = False, shared_events: list[str] | None = None) -> None:
        self.fail = fail
        self.calls: list[FaultDraftCandidate] = []
        self.events: list[str] = []
        self.shared_events = shared_events

    async def create_from_fault(
        self, *, identity: PlatformIdentity, candidate: FaultDraftCandidate
    ) -> ProcurementDraftResult:
        del identity
        self.calls.append(candidate)
        self.events.append("create")
        if self.shared_events is not None:
            self.shared_events.append("create")
        if self.fail:
            raise RuntimeError("backend unavailable")
        return ProcurementDraftResult(
            requirement_id=9001,
            requirement_no="PR-FAULT-9001",
            version=3,
        )


def _knowledge() -> MarkdownKnowledgeSearch:
    root = Path(__file__).resolve().parents[2] / "knowledge" / "fault-guidance"
    return MarkdownKnowledgeSearch(MarkdownKnowledgeLoader(root).load())


def _candidate(quantity: str = "3") -> CandidateItem:
    return CandidateItem(
        item_kind=PurchaseItemKind.COMPONENT,
        item_name="蓄电池",
        quantity=Decimal(quantity),
        unit="块",
        item_evidence="KNOWLEDGE:UPS-BATTERY-001",
        quantity_evidence="USER_CONFIRMED",
    )


def _service(
    orchestrator: ScriptedOrchestrator,
    repository: MemoryFaultStateRepository,
    drafts: RecordingDraftService,
    *,
    knowledge: MarkdownKnowledgeSearch | None = None,
) -> FaultGuidanceService:
    return FaultGuidanceService(
        state_repository=repository,
        asset_provider=AssetProvider(),
        knowledge_search=knowledge or _knowledge(),
        orchestrator=orchestrator,
        validator=FaultDraftValidator(),
        procurement_draft_service=drafts,
        history_provider=EmptyHistory(),
    )


def _identity() -> PlatformIdentity:
    return PlatformIdentity.create(PlatformType.TEST_PLATFORM, "fault-user")


async def _send(service: FaultGuidanceService, message: str) -> FaultGuidanceResponse:
    return await service.handle_message(
        identity=_identity(),
        conversation_id=7001,
        user_message=message,
    )


async def test_ups_battery_fault_end_to_end_requires_confirmation() -> None:
    repository = MemoryFaultStateRepository()
    drafts = RecordingDraftService(shared_events=repository.events)
    orchestrator = ScriptedOrchestrator(
        FaultDecision(
            action=FaultAction.ASK,
            reply="具体是什么告警？",
            issue_summary="2号UPS最近老报警",
        ),
        FaultDecision(
            action=FaultAction.ASK,
            reply="之前有没有做过蓄电池检测？",
            confirmed_facts_updates={"alarm_code": "BATTERY FAULT"},
            knowledge_refs_add=["UPS-BATTERY-001"],
        ),
        FaultDecision(
            action=FaultAction.PROPOSE_ITEM,
            reply="已整理候选项",
            confirmed_facts_updates={
                "inspection_done": True,
                "abnormal_battery_count": 3,
            },
            knowledge_refs_add=["UPS-BATTERY-001"],
            candidate_items=[_candidate()],
        ),
        FaultDecision(
            action=FaultAction.DIRECT_TO_PROCUREMENT,
            reply="用户确认",
            candidate_items=[_candidate("99")],
        ),
    )
    service = _service(orchestrator, repository, drafts)

    assert (await _send(service, "2号UPS最近老报警")).reply == "具体是什么告警？"
    second = await _send(service, "BATTERY FAULT")
    assert "检测" in second.reply
    assert orchestrator.contexts[1].fault_state.issue_summary == "2号UPS最近老报警"
    assert orchestrator.contexts[1].knowledge_results[0].knowledge_id == "UPS-BATTERY-001"
    proposal = await _send(service, "做过了，有3块不行")
    assert "蓄电池 × 3块" in proposal.reply
    assert drafts.calls == []
    saved = await repository.get(7001)
    assert saved is not None
    assert saved.confirmed_facts["alarm_code"] == "BATTERY FAULT"
    assert saved.knowledge_refs == ["UPS-BATTERY-001"]

    completed = await _send(service, "确认")

    assert completed.procurement_draft_ref == "requirement:9001"
    assert len(drafts.calls) == 1
    handoff = drafts.calls[0]
    assert handoff.source_asset_ref == "asset:108"
    assert handoff.items[0].item_name == "蓄电池"
    assert handoff.items[0].quantity == Decimal("3")
    assert handoff.items[0].unit == "块"
    assert "2号UPS最近老报警" in handoff.application_reason
    assert await repository.get(7001) is None
    assert repository.events[-2:] == ["create", "delete"]


async def test_candidate_change_requires_a_new_confirmation() -> None:
    repository = MemoryFaultStateRepository()
    repository.states["7001"] = FaultState(
        source_asset_ref="asset:108", candidate_items=[_candidate()]
    )
    drafts = RecordingDraftService()
    service = _service(
        ScriptedOrchestrator(
            FaultDecision(
                action=FaultAction.PROPOSE_ITEM,
                reply="已修改",
                candidate_items=[_candidate("4")],
            ),
            FaultDecision(action=FaultAction.DIRECT_TO_PROCUREMENT, reply="确认"),
        ),
        repository,
        drafts,
    )

    response = await _send(service, "不对，改成4块")
    assert "蓄电池 × 4块" in response.reply
    assert drafts.calls == []
    await _send(service, "确认")
    assert drafts.calls[0].items[0].quantity == Decimal("4")


@pytest.mark.parametrize(
    "candidate",
    [
        CandidateItem(
            item_kind=PurchaseItemKind.COMPONENT,
            item_name="蓄电池",
            quantity=None,
            unit="块",
        ),
        _candidate("-3"),
    ],
)
async def test_invalid_or_incomplete_candidate_never_creates_draft(
    candidate: CandidateItem,
) -> None:
    repository = MemoryFaultStateRepository()
    drafts = RecordingDraftService()
    service = _service(
        ScriptedOrchestrator(
            FaultDecision(
                action=FaultAction.PROPOSE_ITEM,
                reply="候选",
                candidate_items=[candidate],
            )
        ),
        repository,
        drafts,
    )
    response = await _send(service, "有电池异常")
    assert response.action is FaultAction.ASK
    assert drafts.calls == []
    assert await repository.get(7001) is not None


async def test_switching_asset_resets_old_candidate() -> None:
    repository = MemoryFaultStateRepository()
    repository.states["7001"] = FaultState(
        source_asset_ref="asset:108",
        issue_summary="2号UPS故障",
        candidate_items=[_candidate()],
    )
    orchestrator = ScriptedOrchestrator(
        FaultDecision(action=FaultAction.ASK, reply="3号UPS是什么故障？")
    )
    service = _service(orchestrator, repository, RecordingDraftService())
    await _send(service, "3号UPS最近报警")
    context = orchestrator.contexts[0]
    assert context.fault_state.source_asset_ref == "asset:205"
    assert context.fault_state.candidate_items == []
    assert "reset" in repository.events


async def test_draft_failure_preserves_confirmed_candidate() -> None:
    repository = MemoryFaultStateRepository()
    repository.states["7001"] = FaultState(
        source_asset_ref="asset:108",
        issue_summary="UPS电池故障",
        candidate_items=[_candidate()],
    )
    drafts = RecordingDraftService(fail=True)
    service = _service(
        ScriptedOrchestrator(FaultDecision(action=FaultAction.DIRECT_TO_PROCUREMENT, reply="确认")),
        repository,
        drafts,
    )
    with pytest.raises(RuntimeError, match="backend unavailable"):
        await _send(service, "确认")
    state = await repository.get(7001)
    assert state is not None
    assert state.candidate_items == [_candidate()]
    assert "delete" not in repository.events


async def test_direct_purchase_expression_still_gets_confirmation() -> None:
    repository = MemoryFaultStateRepository()
    drafts = RecordingDraftService()
    direct = CandidateItem(
        item_kind=PurchaseItemKind.COMPONENT,
        item_name="功率模块",
        quantity=Decimal("1"),
        unit="块",
        quantity_evidence="USER_EXPLICIT_REQUEST",
    )
    service = _service(
        ScriptedOrchestrator(
            FaultDecision(
                action=FaultAction.DIRECT_TO_PROCUREMENT,
                reply="明确采购",
                candidate_items=[direct],
            ),
            FaultDecision(action=FaultAction.DIRECT_TO_PROCUREMENT, reply="确认"),
        ),
        repository,
        drafts,
    )
    first = await _send(service, "2号UPS坏了一块功率模块，帮我采购1块")
    assert first.action is FaultAction.PROPOSE_ITEM
    assert "是否按这个采购需求继续" in first.reply
    assert drafts.calls == []
    await _send(service, "确认")
    assert len(drafts.calls) == 1


async def test_explicit_cancel_resets_state_without_orchestrator() -> None:
    repository = MemoryFaultStateRepository()
    repository.states["7001"] = FaultState(candidate_items=[_candidate()])
    orchestrator = ScriptedOrchestrator()
    response = await _send(_service(orchestrator, repository, RecordingDraftService()), "取消")
    assert "取消" in response.reply
    assert await repository.get(7001) is None
    assert orchestrator.contexts == []


async def test_empty_knowledge_results_still_reach_orchestrator() -> None:
    repository = MemoryFaultStateRepository()
    orchestrator = ScriptedOrchestrator(
        FaultDecision(action=FaultAction.ASK, reply="请补充具体故障现象")
    )
    service = _service(
        orchestrator,
        repository,
        RecordingDraftService(),
        knowledge=MarkdownKnowledgeSearch(FaultKnowledgeRepository()),
    )
    response = await _send(service, "柴油发电机燃油泄漏")
    assert response.action is FaultAction.ASK
    assert orchestrator.contexts[0].knowledge_results == []


async def test_procurement_draft_service_uses_existing_fault_draft_contract() -> None:
    user = CurrentUser(
        employee_id=1,
        name="测试需求人",
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=RoleCode.APPLICANT, role_name="需求人"),),
        buildings=(UserBuilding(building_id=1, building_name="一号楼", is_primary=True),),
    )
    backend = FakeBackendClient(user)
    result = await ProcurementDraftService(backend).create_from_fault(
        identity=_identity(),
        candidate=FaultDraftCandidate(
            source_asset_ref=None,
            application_reason="UPS功率模块故障；拟采购功率模块×1块，用于故障处理。",
            items=[
                CandidateItem(
                    item_kind=PurchaseItemKind.COMPONENT,
                    item_name="功率模块",
                    quantity=Decimal("1"),
                    unit="块",
                    quantity_evidence="USER_EXPLICIT_REQUEST",
                )
            ],
        ),
    )
    detail = await backend.get_requirement(
        identity=_identity(), requirement_id=result.requirement_id
    )
    assert detail.request_type.value == "FAULT"
    assert detail.applicant_fields.application_reason == (
        "UPS功率模块故障；拟采购功率模块×1块，用于故障处理。"
    )
    assert detail.items[0].item_name == "功率模块"
    assert detail.items[0].quantity == "1"
