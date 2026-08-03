from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.assistant.agent_tools import (
    PreparePurchasePrefillArgs,
    PreparePurchasePrefillTool,
    QueryPurchaseRequestsArgs,
    QueryPurchaseRequestsTool,
    QuerySupplierProfileArgs,
    QuerySupplierProfileTool,
    RecommendProductOptionsArgs,
    RecommendProductOptionsTool,
    UpdatePurchaseDraftArgs,
    UpdatePurchaseDraftTool,
    UpdatePurchaseExecutionDraftArgs,
    UpdatePurchaseExecutionDraftTool,
    UpdateReviewDraftArgs,
    UpdateReviewDraftTool,
    UpdateWarehouseReceiptDraftArgs,
    UpdateWarehouseReceiptDraftTool,
)
from procurement_platform.application.assistant.supplier_recommendation import (
    RecommendSuppliersForRequirementArgs,
    RecommendSuppliersForRequirementTool,
)
from procurement_platform.application.assistant.temporal_range_resolver import (
    TemporalRangeResolver,
)
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.application.assistant.tools import ToolRegistry
from procurement_platform.domain.assistant import AssistantToolContext
from procurement_platform.domain.enums import (
    AllowedRequirementAction,
    PlatformType,
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ApplicantFields,
    ProductRecommendation,
    ProductRecommendations,
    PurchaseFields,
    PurchaseHistoryItem,
    PurchaseHistoryRecommendations,
    PurchaseRecord,
    RequirementBuilding,
    RequirementDetail,
    RequirementHandler,
    ReviewFields,
    SupplierBlacklistSummary,
    SupplierDetail,
    WarehouseFields,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def user(role: RoleCode, employee_id: int = 1) -> CurrentUser:
    return CurrentUser(
        employee_id=employee_id,
        name=role.value,
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=role),),
        buildings=(UserBuilding(building_id=1, building_name="一号楼", is_primary=True),),
    )


def identity(role: RoleCode) -> PlatformIdentity:
    return PlatformIdentity(PlatformType.FEISHU, f"ou_{role.value.lower()}", "request")


def context(role: RoleCode, *, conversation_id: int = 1) -> AssistantToolContext:
    return AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id=f"ou_{role.value.lower()}",
        conversation_id=conversation_id,
        external_conversation_id="oc_1",
        external_message_id="om_1",
        current_time=datetime(2026, 8, 3, 12, tzinfo=UTC),
        timezone_name="Asia/Shanghai",
        current_user=user(role),
    )


def detail(
    role: RoleCode,
    status: RequirementStatus,
    *,
    requirement_id: int = 1,
    version: int = 1,
) -> RequirementDetail:
    handler = RequirementHandler(employee_id=1, name=role.value)
    return RequirementDetail(
        requirement_id=requirement_id,
        requirement_no=f"PR-{requirement_id}",
        status=status,
        version=version,
        building=RequirementBuilding(building_id=1, building_name="一号楼"),
        current_handler=handler,
        applicant_fields=ApplicantFields(
            device_profession="算力服务器",
            device_name="服务器",
            brand="戴尔",
            model="R750",
            quantity="2",
            unit="台",
            application_reason="扩容",
        ),
        review_fields=ReviewFields(proposed_supplier_id=10, proposed_supplier_name="供应商A"),
        missing_fields=(),
        allowed_actions=(
            AllowedRequirementAction.UPDATE_APPLICANT_FIELDS,
            AllowedRequirementAction.UPDATE_REVIEW_FIELDS,
            AllowedRequirementAction.UPDATE_PURCHASE_FIELDS,
            AllowedRequirementAction.UPDATE_WAREHOUSE_FIELDS,
        ),
        fields_complete=True,
    )


@pytest.mark.parametrize(
    ("expression", "start", "end"),
    [
        ("昨天", "2026-08-02", "2026-08-03"),
        ("上周三", "2026-07-29", "2026-07-30"),
        ("上周", "2026-07-27", "2026-08-03"),
        ("本月", "2026-08-01", "2026-09-01"),
        ("最近三天", "2026-08-01", "2026-08-04"),
    ],
)
def test_temporal_range_resolver(expression: str, start: str, end: str) -> None:
    result = TemporalRangeResolver().resolve(expression, now=datetime(2026, 8, 3, 12, tzinfo=UTC))
    assert result.start.date().isoformat() == start
    assert result.end_exclusive.date().isoformat() == end


def test_tool_policy_matches_task9_role_matrix() -> None:
    policy = ToolPolicy()
    assert policy.allowed_tool_names(
        current_user=user(RoleCode.APPLICANT), active_requirement=None
    ) == frozenset(
        {"query_purchase_requests", "recommend_product_options", "update_purchase_draft"}
    )
    assert (
        len(
            policy.allowed_tool_names(
                current_user=user(RoleCode.BUILDING_MANAGER), active_requirement=None
            )
        )
        == 3
    )
    assert (
        len(
            policy.allowed_tool_names(
                current_user=user(RoleCode.PURCHASER), active_requirement=None
            )
        )
        == 4
    )
    assert (
        len(
            policy.allowed_tool_names(
                current_user=user(RoleCode.WAREHOUSE_MANAGER), active_requirement=None
            )
        )
        == 2
    )


def test_registry_contains_only_task9_tools_and_no_formal_actions() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    registry = ToolRegistry()
    for tool in (
        QueryPurchaseRequestsTool(client),
        RecommendProductOptionsTool(client),
        UpdatePurchaseDraftTool(client),
        RecommendSuppliersForRequirementTool(client),
        UpdateReviewDraftTool(client),
        QuerySupplierProfileTool(client),
        PreparePurchasePrefillTool(client),
        UpdatePurchaseExecutionDraftTool(client),
        UpdateWarehouseReceiptDraftTool(client),
    ):
        registry.register(tool)
    assert registry.registered_names == frozenset(
        {
            "query_purchase_requests",
            "recommend_product_options",
            "update_purchase_draft",
            "recommend_suppliers_for_requirement",
            "update_review_draft",
            "query_supplier_profile",
            "prepare_purchase_prefill",
            "update_purchase_execution_draft",
            "update_warehouse_receipt_draft",
        }
    )
    assert not registry.registered_names.intersection(
        {"submit_review", "reject_requirement", "start_purchase", "complete_requirement"}
    )


@pytest.mark.asyncio
async def test_query_purchase_requests_uses_backend_time_filter_and_returns_latest_detail() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    client.seed_requirement(detail(RoleCode.APPLICANT, RequirementStatus.DRAFT))
    client.purchase_records.append(
        PurchaseRecord(
            requirement_id=1,
            requirement_no="PR-1",
            device_name="服务器",
            status=RequirementStatus.DRAFT,
            created_at=datetime(2026, 8, 3, 1, tzinfo=UTC),
        )
    )
    result = await QueryPurchaseRequestsTool(client).execute(
        args=QueryPurchaseRequestsArgs(operation="SEARCH", time_expression="今天"),
        context=context(RoleCode.APPLICANT),
    )
    assert result.status == "SUCCESS"
    assert result.requirement_id == 1
    assert client.call_counts["list_purchase_records"] == 1
    assert client.call_counts["get_requirement"] == 1


@pytest.mark.asyncio
async def test_product_recommendation_is_deduplicated_and_saved_to_session() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.APPLICANT), current_action="ASSISTANT_CHAT"
    )
    item = ProductRecommendation(
        brand="戴尔",
        model="R750",
        historical_count=3,
        last_purchased_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    client.product_recommendations = ProductRecommendations(items=(item, item))
    result = await RecommendProductOptionsTool(client).execute(
        args=RecommendProductOptionsArgs(device_name="服务器"),
        context=context(RoleCode.APPLICANT, conversation_id=conversation.conversation_id),
    )
    state = await client.get_agent_state(
        identity=identity(RoleCode.APPLICANT), conversation_id=conversation.conversation_id
    )
    assert result.status == "SUCCESS"
    assert len(result.candidates) == 1
    assert state.last_recommendations[0].kind == "PRODUCT_RECOMMENDATION"


@pytest.mark.asyncio
async def test_applicant_draft_creates_single_building_requirement_and_never_submits() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.APPLICANT), current_action="ASSISTANT_CHAT"
    )
    result = await UpdatePurchaseDraftTool(client).execute(
        args=UpdatePurchaseDraftArgs(
            device_profession="算力服务器",
            device_name="服务器",
            quantity="1",
            unit="台",
            application_reason="扩容",
        ),
        context=context(RoleCode.APPLICANT, conversation_id=conversation.conversation_id),
    )
    assert result.status == "SUCCESS"
    assert result.fields_complete is True
    assert client.call_counts["create_requirement"] == 1
    assert client.call_counts["submit_review"] == 0


@pytest.mark.asyncio
async def test_review_draft_resolves_stable_supplier_reference_and_does_not_submit() -> None:
    manager = user(RoleCode.BUILDING_MANAGER)
    client = FakeBackendClient(manager)
    client.seed_requirement(detail(RoleCode.BUILDING_MANAGER, RequirementStatus.PENDING_REVIEW))
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.BUILDING_MANAGER), current_action="ASSISTANT_CHAT"
    )
    ctx = context(RoleCode.BUILDING_MANAGER, conversation_id=conversation.conversation_id)
    await RecommendSuppliersForRequirementTool(client).execute(
        args=RecommendSuppliersForRequirementArgs(requirement_id=1), context=ctx
    )
    result = await UpdateReviewDraftTool(client).execute(
        args=UpdateReviewDraftArgs(requirement_id=1, proposed_supplier_ref="supplier:10"),
        context=ctx,
    )
    assert result.status == "SUCCESS"
    assert client.call_counts["submit_purchaser"] == 0


@pytest.mark.asyncio
async def test_supplier_profile_is_exact_and_preserves_masked_account() -> None:
    client = FakeBackendClient(user(RoleCode.PURCHASER))
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            supplier_tax_number="91310000TEST",
            bank_account="****1234",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
    result = await QuerySupplierProfileTool(client).execute(
        args=QuerySupplierProfileArgs(
            supplier_query="供应商A",
            requested_fields=("UNIFIED_SOCIAL_CREDIT_CODE", "BANK_ACCOUNT"),
        ),
        context=context(RoleCode.PURCHASER),
    )
    assert result.status == "SUCCESS"
    assert result.exact_render_required is True
    assert "****1234" in (result.rendered_text or "")


@pytest.mark.asyncio
async def test_purchase_prefill_uses_selected_supplier_and_tax_is_never_exact() -> None:
    purchaser = user(RoleCode.PURCHASER)
    client = FakeBackendClient(purchaser)
    current = detail(RoleCode.PURCHASER, RequirementStatus.PENDING_PURCHASE)
    historical = detail(
        RoleCode.PURCHASER, RequirementStatus.COMPLETED, requirement_id=2
    ).model_copy(update={"purchase_fields": PurchaseFields(tax_rate="13")})
    client.seed_requirement(current)
    client.seed_requirement(historical)
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            bank_name="测试银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
    client.purchase_history_recommendations = PurchaseHistoryRecommendations(
        items=(
            PurchaseHistoryItem(
                requirement_id=2,
                device_name="服务器",
                brand="戴尔",
                model="R750",
                quantity="1",
                supplier_id=10,
                supplier_name="供应商A",
                actual_total_price="100",
                purchased_at=datetime(2026, 7, 1, tzinfo=UTC),
                blacklist_status="INACTIVE",
            ),
        )
    )
    result = await PreparePurchasePrefillTool(client).execute(
        args=PreparePurchasePrefillArgs(requirement_id=1), context=context(RoleCode.PURCHASER)
    )
    tax = next(item for item in result.fields if item.field_name == "tax_rate")
    assert result.status == "SUCCESS"
    assert tax.resolution == "RECOMMENDED"
    assert all(
        item.resolution != "EXACT" for item in result.fields if item.field_name == "tax_rate"
    )


@pytest.mark.asyncio
async def test_purchase_execution_calculates_decimal_total_and_never_submits() -> None:
    client = FakeBackendClient(user(RoleCode.PURCHASER))
    client.seed_requirement(detail(RoleCode.PURCHASER, RequirementStatus.PURCHASING))
    result = await UpdatePurchaseExecutionDraftTool(client).execute(
        args=UpdatePurchaseExecutionDraftArgs(
            requirement_id=1,
            actual_unit_price="10.25",
            tax_rate="13",
            purchased_at=datetime(2026, 8, 3, tzinfo=UTC),
        ),
        context=context(RoleCode.PURCHASER),
    )
    assert result.status == "SUCCESS"
    assert result.actual_total_price == "20.50"
    assert client.call_counts["submit_warehouse"] == 0


@pytest.mark.asyncio
async def test_warehouse_draft_requires_remark_for_short_receipt_and_never_completes() -> None:
    client = FakeBackendClient(user(RoleCode.WAREHOUSE_MANAGER))
    client.seed_requirement(
        detail(RoleCode.WAREHOUSE_MANAGER, RequirementStatus.PENDING_WAREHOUSE).model_copy(
            update={"warehouse_fields": WarehouseFields()}
        )
    )
    tool = UpdateWarehouseReceiptDraftTool(client)
    missing = await tool.execute(
        args=UpdateWarehouseReceiptDraftArgs(
            requirement_id=1, received_quantity="1", warehouse_location="A-01"
        ),
        context=context(RoleCode.WAREHOUSE_MANAGER),
    )
    saved = await tool.execute(
        args=UpdateWarehouseReceiptDraftArgs(
            requirement_id=1,
            received_quantity="1",
            warehouse_location="A-01",
            receipt_remark="少收一台",
        ),
        context=context(RoleCode.WAREHOUSE_MANAGER),
    )
    assert missing.status == "NEED_MORE_INFORMATION"
    assert saved.status == "SUCCESS"
    assert client.call_counts["complete_requirement"] == 0
