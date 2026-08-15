from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.assistant.capabilities.intelligence import (
    CompareProductsArgs,
    CompareProductsCapability,
    CompareSuppliersArgs,
    CompareSuppliersCapability,
    HistoricalPurchaseRanker,
)
from procurement_platform.application.assistant.task_context_service import (
    AgentTaskStateService,
    ApplicationReasonComposer,
    BusinessFactsBuilder,
    ReferenceStore,
)
from procurement_platform.domain.assistant import AssistantToolContext
from procurement_platform.domain.assistant_context import (
    AgentTaskState,
    PendingChoice,
    StoredReference,
)
from procurement_platform.domain.assistant_session import (
    AgentSessionStateUpdate,
    RecommendationReference,
)
from procurement_platform.domain.enums import PlatformType, RequirementStatus, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ApplicantFields,
    PurchaseRecord,
    RequirementBuilding,
    RequirementDetail,
    SupplierBlacklistSummary,
    SupplierDetail,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def _user() -> CurrentUser:
    return CurrentUser(
        employee_id=1,
        name="Test",
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=RoleCode.APPLICANT), UserRole(role_code=RoleCode.PURCHASER)),
        buildings=(UserBuilding(building_id=3, building_name="三号楼", is_primary=True),),
    )


def _identity() -> PlatformIdentity:
    return PlatformIdentity.create(PlatformType.FEISHU, "ou_intelligence")


def _context(conversation_id: int) -> AssistantToolContext:
    return AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id="ou_intelligence",
        conversation_id=conversation_id,
        external_conversation_id="oc_intelligence",
        external_message_id="om_intelligence",
        current_time=datetime(2026, 8, 15, tzinfo=UTC),
        timezone_name="Asia/Shanghai",
        current_user=_user(),
    )


def _detail() -> RequirementDetail:
    return RequirementDetail(
        requirement_id=10,
        requirement_no="PR-10",
        status=RequirementStatus.DRAFT,
        version=2,
        building=RequirementBuilding(building_id=3, building_name="三号楼"),
        applicant_fields=ApplicantFields(device_name="UPS 功率模块", brand="A", model="M1"),
        missing_fields=(),
        allowed_actions=(),
    )


def test_business_facts_are_built_from_authoritative_models() -> None:
    facts = BusinessFactsBuilder.build(_user(), _detail())
    assert facts.requirement_id == 10
    assert facts.requirement_version == 2
    assert facts.authoritative_fields["model"] == "M1"
    assert facts.building_ids == (3,)


def test_application_reason_uses_only_supplied_facts() -> None:
    reason = ApplicationReasonComposer.compose(
        building_name="3号楼",
        device_name="UPS 功率模块",
        symptom_text="持续旁路报警",
    )
    assert "3号楼" in reason
    assert "UPS 功率模块" in reason
    assert "持续旁路报警" in reason
    assert "品牌" not in reason
    assert "金额" not in reason
    assert "紧急" not in reason


@pytest.mark.asyncio
async def test_task_state_and_reference_store_round_trip() -> None:
    client = FakeBackendClient(_user())
    identity = _identity()
    conversation = await client.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    service = AgentTaskStateService(client)
    task = AgentTaskState(
        active_goal="CREATE_PURCHASE_DRAFT",
        known={"quantity": "2"},
        unresolved=("product",),
        pending_choice=PendingChoice(
            candidate_refs=("product:a", "product:b"), source_capability="compare_products"
        ),
    )
    await service.save(
        identity=identity,
        conversation_id=conversation.conversation_id,
        session=None,
        task=task,
    )
    state = await client.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert service.from_session(state) == task

    store = ReferenceStore(client)
    await store.save(
        identity=identity,
        conversation_id=conversation.conversation_id,
        state=state,
        references=(
            StoredReference(
                reference_id="product:a",
                entity_type="PRODUCT_RECOMMENDATION",
                source_capability="diagnose_procurement_need",
                label="A M1",
                payload={"brand": "A", "model": "M1"},
            ),
        ),
    )
    saved = await client.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert ReferenceStore.resolve(saved, "product:a").payload["model"] == "M1"


def test_similar_purchase_ranking_is_stable_and_evidence_backed() -> None:
    record = PurchaseRecord(
        requirement_id=1,
        requirement_no="PR-1",
        device_name="UPS 功率模块",
        brand="A",
        model="M1",
        status=RequirementStatus.COMPLETED,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        completed_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    first = HistoricalPurchaseRanker.score(
        record,
        building_match=True,
        device_name="UPS 功率模块",
        brand="A",
        model="M1",
        now=datetime(2026, 8, 15, tzinfo=UTC),
    )
    second = HistoricalPurchaseRanker.score(
        record,
        building_match=True,
        device_name="UPS 功率模块",
        brand="A",
        model="M1",
        now=datetime(2026, 8, 15, tzinfo=UTC),
    )
    assert first == second
    assert first[0] > 0.9
    assert "型号完全匹配" in first[1]


@pytest.mark.asyncio
async def test_product_comparison_recommends_only_from_persisted_evidence() -> None:
    client = FakeBackendClient(_user())
    identity = _identity()
    conversation = await client.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    await client.update_agent_state(
        identity=identity,
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            collected_data={
                "product_candidate:product:a:count": 2,
                "product_candidate:product:b:count": 5,
            },
            last_recommendations=(
                # labels are display-only; comparison uses persisted evidence.
                RecommendationReference(
                    reference_id="product:a",
                    kind="PRODUCT_RECOMMENDATION",
                    label="A",
                ),
                RecommendationReference(
                    reference_id="product:b",
                    kind="PRODUCT_RECOMMENDATION",
                    label="B",
                ),
            ),
        ),
    )
    result = await CompareProductsCapability(client).execute(
        args=CompareProductsArgs(candidate_refs=("product:a", "product:b")),
        context=_context(conversation.conversation_id),
    )
    assert result.recommended_ref == "product:b"
    assert result.insufficient_data


@pytest.mark.asyncio
async def test_supplier_comparison_hard_blocks_blacklisted_supplier() -> None:
    client = FakeBackendClient(_user())
    identity = _identity()
    conversation = await client.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    client.seed_supplier(SupplierDetail(supplier_id=1, supplier_name="Safe"))
    client.seed_supplier(
        SupplierDetail(
            supplier_id=2,
            supplier_name="Blocked",
            blacklist=SupplierBlacklistSummary(active=True, reason="risk"),
        )
    )
    await client.update_agent_state(
        identity=identity,
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            last_recommendations=(
                RecommendationReference(
                    reference_id="supplier:1",
                    kind="SUPPLIER_RECOMMENDATION",
                    label="Safe",
                ),
                RecommendationReference(
                    reference_id="supplier:2",
                    kind="SUPPLIER_RECOMMENDATION",
                    label="Blocked",
                ),
            )
        ),
    )
    result = await CompareSuppliersCapability(client).execute(
        args=CompareSuppliersArgs(supplier_refs=("supplier:1", "supplier:2")),
        context=_context(conversation.conversation_id),
    )
    assert result.recommended_ref == "supplier:1"
    assert result.blocked_refs == ("supplier:2",)
