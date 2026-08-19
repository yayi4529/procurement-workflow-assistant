# ruff: noqa: RUF001

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from procurement_platform.adapters.knowledge import MarkdownKnowledgeLoader
from procurement_platform.application.fault_guidance import (
    FaultDraftValidator,
    FaultGuidanceService,
    MarkdownKnowledgeSearch,
)
from procurement_platform.application.fault_guidance.service import AssetResolution
from procurement_platform.domain.assets import (
    AssetSummary,
    BuildingSummary,
    EquipmentCategorySummary,
)
from procurement_platform.domain.enums import FaultAction, PurchaseItemKind
from procurement_platform.domain.fault_guidance import (
    CandidateItem,
    FaultDecision,
    FaultGuidanceResponse,
)
from procurement_platform.domain.identity import PlatformIdentity
from tests.integration.test_fault_guidance_flow import (
    EmptyHistory,
    MemoryFaultStateRepository,
    RecordingDraftService,
    ScriptedOrchestrator,
    _identity,
)

ROOT = Path(__file__).resolve().parents[2]


def _asset(category_code: str) -> AssetSummary:
    category = EquipmentCategorySummary(
        category_id=20,
        parent_category_id=None,
        category_code=category_code,
        category_name=category_code,
        category_level=2,
        description=None,
        sort_order=1,
        status="ACTIVE",
    )
    return AssetSummary(
        asset_id=500,
        asset_code=f"TEST-{category_code}-500",
        asset_name=f"测试{category_code}设备",
        category_id=20,
        model_id=None,
        building_id=1,
        location="测试机房",
        serial_number=None,
        status="ACTIVE",
        criticality="HIGH",
        commissioned_at=date(2025, 1, 1),
        warranty_end_at=None,
        configuration=None,
        aliases=(f"测试{category_code}设备",),
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


class FixedCategoryAssetProvider:
    def __init__(self, category: str) -> None:
        self.asset = _asset(category)

    async def resolve(
        self,
        *,
        identity: PlatformIdentity,
        user_message: str,
        current_asset_ref: str | None,
    ) -> AssetResolution:
        del identity, user_message, current_asset_ref
        return AssetResolution(asset=self.asset, identified_in_message=True)


def _search() -> MarkdownKnowledgeSearch:
    repository = MarkdownKnowledgeLoader(ROOT / "knowledge/fault-guidance").load()
    return MarkdownKnowledgeSearch(repository)


def _candidate(
    *, item_name: str, quantity: str | None, unit: str, knowledge_id: str
) -> CandidateItem:
    return CandidateItem(
        item_kind=PurchaseItemKind.COMPONENT,
        item_name=item_name,
        quantity=Decimal(quantity) if quantity is not None else None,
        unit=unit,
        brand=None,
        model=None,
        item_evidence=f"KNOWLEDGE:{knowledge_id}",
        quantity_evidence="USER_CONFIRMED" if quantity is not None else None,
    )


def _service(
    *,
    category: str,
    orchestrator: ScriptedOrchestrator,
    repository: MemoryFaultStateRepository,
    drafts: RecordingDraftService,
) -> FaultGuidanceService:
    return FaultGuidanceService(
        state_repository=repository,
        asset_provider=FixedCategoryAssetProvider(category),
        knowledge_search=_search(),
        orchestrator=orchestrator,
        validator=FaultDraftValidator(),
        procurement_draft_service=drafts,
        history_provider=EmptyHistory(),
    )


async def _send(service: FaultGuidanceService, message: str) -> FaultGuidanceResponse:
    return await service.handle_message(
        identity=_identity(), conversation_id=8101, user_message=message
    )


@pytest.mark.parametrize(
    (
        "category",
        "initial_message",
        "confirmed_message",
        "knowledge_id",
        "item_name",
        "quantity",
        "unit",
    ),
    [
        (
            "UPS",
            "FAN FAULT",
            "检测确认UPS风扇坏了2个，需要更换",
            "UPS-FAN-001",
            "UPS 风扇",
            "2",
            "个",
        ),
        (
            "SERVER",
            "HDD FAILURE",
            "检测确认2块HDD坏了，需要更换",
            "SERVER-HDD-001",
            "服务器 HDD",
            "2",
            "块",
        ),
        (
            "SERVER",
            "DIMM ERROR",
            "确认2条内存故障，需要更换",
            "SERVER-MEMORY-001",
            "服务器内存",
            "2",
            "条",
        ),
        (
            "TRANSMISSION",
            "传输设备端口 down 了",
            "排除光纤后检测确认 TRANSCEIVER FAULT，1只需要更换",
            "TRANSMISSION-OPTICAL-TRANSCEIVER-001",
            "光模块",
            "1",
            "只",
        ),
        (
            "COOLING_PUMP",
            "冷却泵漏水",
            "现场确认机械密封损坏，需要更换1个",
            "COOLING-PUMP-MECHANICAL-SEAL-001",
            "水泵机械密封",
            "1",
            "个",
        ),
        (
            "ROOM_ENVIRONMENT",
            "机房高温报警",
            "排除真实高温后确认温湿度传感器故障1个，需要更换",
            "ROOM-TEMP-HUMIDITY-SENSOR-001",
            "温湿度传感器",
            "1",
            "个",
        ),
    ],
)
async def test_representative_p0_scenarios_require_facts_then_user_confirmation(
    category: str,
    initial_message: str,
    confirmed_message: str,
    knowledge_id: str,
    item_name: str,
    quantity: str,
    unit: str,
) -> None:
    candidate = _candidate(
        item_name=item_name,
        quantity=quantity,
        unit=unit,
        knowledge_id=knowledge_id,
    )
    repository = MemoryFaultStateRepository()
    drafts = RecordingDraftService()
    orchestrator = ScriptedOrchestrator(
        FaultDecision(
            action=FaultAction.ASK,
            reply="请确认具体部件本体是否故障、是否需要更换以及数量。",
            issue_summary=initial_message,
        ),
        FaultDecision(
            action=FaultAction.PROPOSE_ITEM,
            reply="现场事实已确认。",
            knowledge_refs_add=[knowledge_id],
            candidate_items=[candidate],
        ),
        FaultDecision(action=FaultAction.DIRECT_TO_PROCUREMENT, reply="用户确认"),
    )
    service = _service(
        category=category,
        orchestrator=orchestrator,
        repository=repository,
        drafts=drafts,
    )

    first = await _send(service, initial_message)
    assert first.action is FaultAction.ASK
    assert drafts.calls == []
    if knowledge_id in {
        "TRANSMISSION-OPTICAL-TRANSCEIVER-001",
        "ROOM-TEMP-HUMIDITY-SENSOR-001",
    }:
        assert orchestrator.contexts[0].knowledge_results == []
    else:
        assert orchestrator.contexts[0].knowledge_results[0].knowledge_id == knowledge_id

    proposal = await _send(service, confirmed_message)
    assert proposal.action is FaultAction.PROPOSE_ITEM
    assert item_name in proposal.reply
    assert drafts.calls == []
    saved = await repository.get(8101)
    assert saved is not None
    assert saved.candidate_items[0].brand is None
    assert saved.candidate_items[0].model is None

    completed = await _send(service, "确认")
    assert completed.action is FaultAction.DIRECT_TO_PROCUREMENT
    assert len(drafts.calls) == 1
    assert drafts.calls[0].items[0].item_name == item_name
    assert drafts.calls[0].items[0].quantity == Decimal(quantity)


@pytest.mark.parametrize(
    ("category", "knowledge_id", "item_name", "unit"),
    [
        ("SERVER", "SERVER-HDD-001", "服务器 HDD", "块"),
        ("SERVER", "SERVER-MEMORY-001", "服务器内存", "条"),
    ],
)
async def test_confirmed_part_without_quantity_never_defaults_to_one(
    category: str, knowledge_id: str, item_name: str, unit: str
) -> None:
    candidate = _candidate(
        item_name=item_name,
        quantity=None,
        unit=unit,
        knowledge_id=knowledge_id,
    )
    repository = MemoryFaultStateRepository()
    drafts = RecordingDraftService()
    service = _service(
        category=category,
        orchestrator=ScriptedOrchestrator(
            FaultDecision(
                action=FaultAction.PROPOSE_ITEM,
                reply="已确认部件故障",
                candidate_items=[candidate],
            )
        ),
        repository=repository,
        drafts=drafts,
    )
    response = await _send(service, "已确认部件故障并需要更换")
    assert response.action is FaultAction.ASK
    assert "quantity" in response.reply
    assert drafts.calls == []


async def test_server_hdd_candidate_change_requires_reconfirmation() -> None:
    first_candidate = _candidate(
        item_name="服务器 HDD", quantity="3", unit="块", knowledge_id="SERVER-HDD-001"
    )
    corrected_candidate = _candidate(
        item_name="服务器 HDD", quantity="4", unit="块", knowledge_id="SERVER-HDD-001"
    )
    repository = MemoryFaultStateRepository()
    drafts = RecordingDraftService()
    service = _service(
        category="SERVER",
        orchestrator=ScriptedOrchestrator(
            FaultDecision(
                action=FaultAction.PROPOSE_ITEM,
                reply="候选3块",
                candidate_items=[first_candidate],
            ),
            FaultDecision(
                action=FaultAction.PROPOSE_ITEM,
                reply="修正为4块",
                candidate_items=[corrected_candidate],
            ),
            FaultDecision(action=FaultAction.DIRECT_TO_PROCUREMENT, reply="用户确认"),
        ),
        repository=repository,
        drafts=drafts,
    )
    assert (await _send(service, "确认3块HDD故障")).action is FaultAction.PROPOSE_ITEM
    corrected = await _send(service, "不是3块，是4块")
    assert corrected.action is FaultAction.PROPOSE_ITEM
    assert "4块" in corrected.reply
    assert drafts.calls == []
    await _send(service, "确认")
    assert drafts.calls[0].items[0].quantity == Decimal("4")
