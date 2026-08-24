import os
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.llm.openai_compatible_llm_client import OpenAICompatibleLlmClient
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
from procurement_platform.bootstrap.container import _build_capability_registry
from procurement_platform.domain.analytics import (
    AnalyticsCatalog,
    AnalyticsField,
    AnalyticsMetric,
    AnalyticsQueryResult,
    AnalyticsView,
)
from procurement_platform.domain.assets import (
    AssetComponent,
    AssetContext,
    AssetSummary,
    BuildingSummary,
    EquipmentCategorySummary,
    EquipmentModelSummary,
)
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantToolDefinition,
    AssistantTurn,
)
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.errors import SessionNotFoundError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.requirement import (
    ProductRecommendation,
    ProductRecommendations,
    SupplierBlacklistSummary,
    SupplierDetail,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole
from procurement_platform.ports.llm_client import LlmClient


class RecordingRealLlm:
    def __init__(self, delegate: LlmClient) -> None:
        self.delegate = delegate
        self.tool_sets: list[frozenset[str]] = []
        self.turns: list[AssistantTurn] = []

    async def complete(
        self,
        *,
        messages: tuple[AssistantMessage, ...],
        tools: tuple[AssistantToolDefinition, ...],
        tool_choice: str | None = None,
    ) -> AssistantTurn:
        self.tool_sets.append(frozenset(tool.name for tool in tools))
        turn = await self.delegate.complete(messages=messages, tools=tools, tool_choice=tool_choice)
        self.turns.append(turn)
        return turn

    async def aclose(self) -> None:
        await self.delegate.aclose()


SKILL_CASES = (
    ("draft-single", RoleCode.APPLICANT, ("我要买1个开关电源",), "create-draft", "AWAITING_CARD"),
    (
        "draft-missing",
        RoleCode.APPLICANT,
        ("我要买环境检测仪", "2个环境检测仪"),
        "create-draft",
        "AWAITING_CARD",
    ),
    (
        "fault-multi",
        RoleCode.APPLICANT,
        ("2号UPS高温并且风扇报警", "2个风扇、4个电容都确认损坏"),
        "fault-procurement",
        "AWAITING_CARD",
    ),
    (
        "product-select",
        RoleCode.APPLICANT,
        ("推荐控制电源品牌型号", "第一个"),
        "product-recommendation",
        "COMPLETED",
    ),
    (
        "product-draft",
        RoleCode.APPLICANT,
        ("推荐控制电源品牌型号", "用第一个创建草稿"),
        "create-draft",
        "AWAITING_USER",
    ),
    (
        "product-draft-quantity",
        RoleCode.APPLICANT,
        ("推荐控制电源品牌型号", "用第一个创建草稿,数量2个"),
        "create-draft",
        "AWAITING_CARD",
    ),
    (
        "new-goal",
        RoleCode.APPLICANT,
        ("推荐控制电源品牌型号", "我要买2个开关电源"),
        "create-draft",
        "AWAITING_CARD",
    ),
    (
        "analytics",
        RoleCode.PURCHASER,
        ("统计今年每月采购金额",),
        "procurement-analytics",
        "COMPLETED",
    ),
    (
        "supplier",
        RoleCode.PURCHASER,
        ("按合作次数和交付周期推荐供应商",),
        "supplier-recommendation",
        "COMPLETED",
    ),
)


@pytest.mark.parametrize(
    ("case_id", "role", "messages", "expected_workflow", "expected_status"), SKILL_CASES
)
@pytest.mark.asyncio
async def test_real_model_drives_full_skill_assistant_service(
    require_real_llm: None,
    case_id: str,
    role: RoleCode,
    messages: tuple[str, ...],
    expected_workflow: str,
    expected_status: str,
) -> None:
    del require_real_llm
    service, backend, llm = _service(role)
    responses = []
    for index, text in enumerate(messages, start=1):
        responses.append(await service.handle(_event(case_id, index, text)))

    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_skill_real_eval")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    try:
        state = await backend.get_agent_state(
            identity=identity, conversation_id=conversation.conversation_id
        )
    except SessionNotFoundError:
        pytest.fail(f"workflow state missing; responses={responses!r}; llm_turns={llm.turns!r}")
    workflow = WorkflowStateService.from_session(state)

    assert workflow is not None
    assert workflow.workflow_name == expected_workflow
    assert workflow.status.value == expected_status, (
        f"workflow={workflow!r}; responses={responses!r}; llm_turns={llm.turns!r}"
    )
    assert all(len(turn.tool_calls) <= 1 for turn in llm.turns)
    mutation_names = {"update_multi_item_draft"}
    mutation_calls = sum(
        1 for turn in llm.turns for call in turn.tool_calls if call.name in mutation_names
    )
    assert mutation_calls <= 1
    if case_id in {"analytics", "supplier"}:
        assert any(ref.startswith("analytics-query:") for ref in workflow.evidence_refs)
    formal_actions = {"submit", "approve", "reject", "start_purchase", "complete"}
    assert all(not names.intersection(formal_actions) for names in llm.tool_sets)


def _service(role: RoleCode) -> tuple[AssistantService, FakeBackendClient, RecordingRealLlm]:
    backend = FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="Skill real eval",
            mobile=None,
            status="ACTIVE",
            roles=(UserRole(role_code=role),),
            buildings=(UserBuilding(building_id=1, building_name="测试楼", is_primary=True),),
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
    backend.seed_asset_context(_ups_asset_context())
    backend.seed_supplier(
        SupplierDetail(
            supplier_id=101,
            supplier_name="TEST-供应商",
            bank_name="TEST-银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
    backend.analytics_catalog = _analytics_catalog()
    backend.analytics_query_result = AnalyticsQueryResult(
        query_id="fake-query",
        columns=("supplier_id", "supplier_name", "purchase_count"),
        rows=(
            {
                "supplier_id": 101,
                "supplier_name": "TEST-供应商",
                "purchase_count": 3,
                "purchase_amount": "1200.00",
                "average_delivery_days": "4.0",
            },
        ),
        row_count=1,
        truncated=False,
        duration_ms=1,
        normalized_sql="SELECT supplier_id FROM analytics_purchase_item_fact",
        synthetic_included=True,
    )
    llm = RecordingRealLlm(
        OpenAICompatibleLlmClient(
            api_key=SecretStr(os.environ["PROCUREMENT_LLM_API_KEY"]),
            model=os.environ["PROCUREMENT_LLM_MODEL"],
            timeout_seconds=float(os.getenv("PROCUREMENT_LLM_TIMEOUT_SECONDS", "30")),
            base_url=os.getenv("PROCUREMENT_LLM_BASE_URL") or None,
        )
    )
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
            tool_executor=ToolExecutor(registry.tool_registry, max_result_chars=20_000),
            max_tool_steps=6,
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
    return service, backend, llm


def _event(case_id: str, index: int, text: str) -> TextMessageEvent:
    return TextMessageEvent(
        event_id=f"TEST-SKILL-EVAL-{case_id}-{index}",
        external_user_id="ou_skill_real_eval",
        external_message_id=f"om-{case_id}-{index}",
        chat_id="oc-skill-real-eval",
        text=text,
    )


def _analytics_catalog() -> AnalyticsCatalog:
    fields = (
        AnalyticsField(name="purchased_at", description="采购时间", data_type="datetime"),
        AnalyticsField(name="actual_total_price", description="采购金额", data_type="decimal"),
        AnalyticsField(name="supplier_id", description="供应商 ID", data_type="integer"),
        AnalyticsField(name="supplier_name", description="供应商名称", data_type="string"),
        AnalyticsField(name="delivery_days", description="交付周期", data_type="integer"),
    )
    return AnalyticsCatalog(
        version="1.0",
        dialect="mysql",
        synthetic_default_included=True,
        views=(
            AnalyticsView(
                name="analytics_purchase_item_fact",
                description="采购项事实",
                grain="request_item_id",
                fields=fields,
            ),
        ),
        metrics=(
            AnalyticsMetric(
                name="采购金额", description="采购金额合计", expression="SUM(actual_total_price)"
            ),
        ),
    )


def _ups_asset_context() -> AssetContext:
    category = EquipmentCategorySummary(
        category_id=10,
        parent_category_id=1,
        category_code="UPS",
        category_name="UPS",
        category_level=2,
        description=None,
        sort_order=1,
        status="ACTIVE",
    )
    model = EquipmentModelSummary(
        model_id=20,
        category_id=10,
        brand="TEST",
        model="UPS-500",
        model_name=None,
        specifications={},
        default_unit="台",
        lifecycle_status="ACTIVE",
        remark=None,
    )
    asset = AssetSummary(
        asset_id=1,
        asset_code="TEST-UPS-02",
        asset_name="2号UPS",
        category_id=10,
        model_id=20,
        building_id=1,
        location="测试楼二层",
        serial_number=None,
        status="ACTIVE",
        criticality="CRITICAL",
        commissioned_at=date(2025, 1, 1),
        warranty_end_at=None,
        configuration={},
        aliases=("2号UPS", "UPS02"),
        redundancy_group=None,
        redundancy_mode=None,
        remark=None,
        version=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        category=category,
        model=model,
        building=BuildingSummary(building_id=1, building_name="测试楼"),
    )
    return AssetContext(
        asset=asset,
        components=(
            AssetComponent(
                component_id=1,
                asset_id=1,
                component_name="UPS 风扇",
                component_category="FAN",
                brand=None,
                model_or_part_no=None,
                quantity=Decimal("2"),
                unit="个",
                status="ALARM",
                replaceable=True,
                remark=None,
            ),
            AssetComponent(
                component_id=2,
                asset_id=1,
                component_name="UPS 电容",
                component_category="CAPACITOR",
                brand=None,
                model_or_part_no=None,
                quantity=Decimal("4"),
                unit="个",
                status="NORMAL",
                replaceable=True,
                remark=None,
            ),
        ),
        relations=(),
        redundancy_peers=(),
    )
