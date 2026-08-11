from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.assistant.agent_tools import (
    FillSelectedSupplierProfileArgs,
    FillSelectedSupplierProfileTool,
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
from procurement_platform.application.assistant.agents.purchaser import PurchaserAgent
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.supplier_recommendation import (
    RecommendSuppliersForRequirementArgs,
    RecommendSuppliersForRequirementTool,
)
from procurement_platform.application.assistant.temporal_range_resolver import (
    TemporalRangeResolver,
)
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantToolContext,
)
from procurement_platform.domain.assistant_session import (
    AgentSessionStateUpdate,
    RecommendationReference,
)
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
        current_user=user(RoleCode.APPLICANT), active_role=RoleCode.APPLICANT
    ) == frozenset(
        {"query_purchase_requests", "recommend_product_options", "update_purchase_draft"}
    )
    assert (
        len(
            policy.allowed_tool_names(
                current_user=user(RoleCode.BUILDING_MANAGER),
                active_role=RoleCode.BUILDING_MANAGER,
            )
        )
        == 4
    )
    assert (
        len(
            policy.allowed_tool_names(
                current_user=user(RoleCode.PURCHASER), active_role=RoleCode.PURCHASER
            )
        )
        == 5
    )
    assert (
        len(
            policy.allowed_tool_names(
                current_user=user(RoleCode.WAREHOUSE_MANAGER),
                active_role=RoleCode.WAREHOUSE_MANAGER,
            )
        )
        == 2
    )


def test_tool_policy_does_not_merge_tools_for_multi_role_user() -> None:
    multi_role = user(RoleCode.APPLICANT).model_copy(
        update={
            "roles": (
                UserRole(role_code=RoleCode.APPLICANT, role_name="Applicant"),
                UserRole(role_code=RoleCode.PURCHASER, role_name="Purchaser"),
            )
        }
    )

    applicant_tools = ToolPolicy().allowed_tool_names(
        current_user=multi_role, active_role=RoleCode.APPLICANT
    )
    purchaser_tools = ToolPolicy().allowed_tool_names(
        current_user=multi_role, active_role=RoleCode.PURCHASER
    )

    assert applicant_tools == frozenset(
        {"query_purchase_requests", "recommend_product_options", "update_purchase_draft"}
    )
    assert "prepare_purchase_prefill" not in applicant_tools
    assert "update_purchase_draft" not in purchaser_tools


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
        FillSelectedSupplierProfileTool(client),
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
            "fill_selected_supplier_profile",
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
    assert result.total_count is None


@pytest.mark.asyncio
async def test_query_purchase_request_detail_resolves_full_requirement_number() -> None:
    client = FakeBackendClient(user(RoleCode.PURCHASER))
    requirement = detail(
        RoleCode.PURCHASER, RequirementStatus.PURCHASING, requirement_id=91092
    ).model_copy(update={"requirement_no": "PR-20260810-5132E77E"})
    client.seed_requirement(requirement)
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            bank_name="测试银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            bank_name="测试银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
    client.purchase_records.append(
        PurchaseRecord(
            requirement_id=91092,
            requirement_no="PR-20260810-5132E77E",
            device_name="UPS功率模块",
            status=RequirementStatus.PURCHASING,
            created_at=datetime(2026, 8, 10, tzinfo=UTC),
        )
    )

    result = await QueryPurchaseRequestsTool(client).execute(
        args=QueryPurchaseRequestsArgs(
            operation="GET_DETAIL", requirement_no="PR-20260810-5132E77E"
        ),
        context=context(RoleCode.PURCHASER),
    )

    assert result.status == "SUCCESS"
    assert result.requirement_id == 91092
    assert result.requirement_no == "PR-20260810-5132E77E"
    assert client.call_counts["list_purchase_records"] == 1
    assert client.call_counts["get_requirement"] == 1


@pytest.mark.asyncio
async def test_query_purchase_requests_returns_backend_total_for_unfiltered_history() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.APPLICANT), current_action="ASSISTANT_CHAT"
    )
    client.purchase_records.extend(
        (
            PurchaseRecord(
                requirement_id=1,
                requirement_no="PR-1",
                device_name="服务器",
                status=RequirementStatus.DRAFT,
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

    result = await QueryPurchaseRequestsTool(client).execute(
        args=QueryPurchaseRequestsArgs(operation="SEARCH", result_limit=2),
        context=context(RoleCode.APPLICANT, conversation_id=conversation.conversation_id),
    )

    assert result.status == "MULTIPLE_MATCHES"
    assert result.total_count == 2


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
async def test_brand_recommendation_deduplicates_brand_and_replaces_old_candidates() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.APPLICANT), current_action="ASSISTANT_CHAT"
    )
    await client.update_agent_state(
        identity=identity(RoleCode.APPLICANT),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            pending_field="brand",
            last_recommendations=(
                RecommendationReference(
                    reference_id="old", kind="PRODUCT_RECOMMENDATION", label="旧"
                ),
            ),
        ),
    )
    client.product_recommendations = ProductRecommendations(
        items=tuple(
            ProductRecommendation(
                brand=brand,
                model=model,
                historical_count=1,
                last_purchased_at=datetime(2026, 7, index, tzinfo=UTC),
            )
            for index, (brand, model) in enumerate(
                (("华为", "A"), ("华为", "B"), ("H3C", "C"), ("锐捷", "D")), start=1
            )
        )
    )
    result = await RecommendProductOptionsTool(client).execute(
        args=RecommendProductOptionsArgs(device_name="交换机"),
        context=context(RoleCode.APPLICANT, conversation_id=conversation.conversation_id),
    )
    state = await client.get_agent_state(
        identity=identity(RoleCode.APPLICANT), conversation_id=conversation.conversation_id
    )
    assert [item.brand for item in result.candidates] == ["华为", "H3C", "锐捷"]
    assert all(item.reference_id != "old" for item in state.last_recommendations)
    assert state.pending_field == "brand"


@pytest.mark.asyncio
async def test_selection_index_resolves_pending_brand_without_guessing_model() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    client.seed_requirement(detail(RoleCode.APPLICANT, RequirementStatus.DRAFT))
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.APPLICANT), current_action="ASSISTANT_CHAT"
    )
    ref = "product:1:test"
    await client.update_agent_state(
        identity=identity(RoleCode.APPLICANT),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            purchase_request_id=1,
            pending_field="brand",
            last_recommendations=(
                RecommendationReference(
                    reference_id=ref, kind="PRODUCT_RECOMMENDATION", label="华为 S5735"
                ),
            ),
            collected_data={
                f"product_candidate:{ref}:brand": "华为",
                f"product_candidate:{ref}:model": "S5735",
            },
        ),
    )
    result = await UpdatePurchaseDraftTool(client).execute(
        args=UpdatePurchaseDraftArgs(selection_index=1),
        context=context(
            RoleCode.APPLICANT, conversation_id=conversation.conversation_id
        ).model_copy(update={"active_requirement_id": 1}),
    )
    latest = await client.get_requirement(identity=identity(RoleCode.APPLICANT), requirement_id=1)
    assert result.status == "SUCCESS"
    assert result.updated_fields == ("brand",)
    assert latest.applicant_fields.brand == "华为"
    assert latest.applicant_fields.model == "R750"


@pytest.mark.asyncio
async def test_selection_index_out_of_range_fails_without_saving() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    client.seed_requirement(detail(RoleCode.APPLICANT, RequirementStatus.DRAFT))
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.APPLICANT), current_action="ASSISTANT_CHAT"
    )
    ref = "product:1:test"
    await client.update_agent_state(
        identity=identity(RoleCode.APPLICANT),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            purchase_request_id=1,
            pending_field="brand",
            last_recommendations=(
                RecommendationReference(
                    reference_id=ref, kind="PRODUCT_RECOMMENDATION", label="华为 S5735"
                ),
            ),
            collected_data={f"product_candidate:{ref}:brand": "华为"},
        ),
    )

    result = await UpdatePurchaseDraftTool(client).execute(
        args=UpdatePurchaseDraftArgs(selection_index=4),
        context=context(
            RoleCode.APPLICANT, conversation_id=conversation.conversation_id
        ).model_copy(update={"active_requirement_id": 1}),
    )

    assert result.status == "INVALID_ARGUMENTS"
    assert client.call_counts["update_applicant_fields"] == 0


@pytest.mark.asyncio
async def test_direct_model_value_completes_applicant_collection() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    client.seed_requirement(detail(RoleCode.APPLICANT, RequirementStatus.DRAFT))
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.APPLICANT), current_action="ASSISTANT_CHAT"
    )
    await client.update_agent_state(
        identity=identity(RoleCode.APPLICANT),
        conversation_id=conversation.conversation_id,
        state=AgentSessionStateUpdate(
            purchase_request_id=1,
            pending_field="model",
            missing_fields=("model",),
        ),
    )

    result = await UpdatePurchaseDraftTool(client).execute(
        args=UpdatePurchaseDraftArgs(model="PEX4"),
        context=context(
            RoleCode.APPLICANT, conversation_id=conversation.conversation_id
        ).model_copy(update={"active_requirement_id": 1}),
    )

    latest = await client.get_requirement(identity=identity(RoleCode.APPLICANT), requirement_id=1)
    assert result.status == "SUCCESS"
    assert result.fields_complete is True
    assert latest.applicant_fields.model == "PEX4"


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
    assert result.fields_complete is False
    assert result.missing_fields == ("brand",)
    assert result.next_missing_field == "brand"
    assert result.updated_fields == (
        "device_profession",
        "device_name",
        "quantity",
        "unit",
        "application_reason",
    )
    assert client.call_counts["create_requirement"] == 1
    assert client.call_counts["update_applicant_fields"] == 1
    assert client.call_counts["submit_review"] == 0


@pytest.mark.asyncio
async def test_device_profession_is_filled_from_unique_same_device_history() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.APPLICANT), current_action="ASSISTANT_CHAT"
    )
    current = detail(RoleCode.APPLICANT, RequirementStatus.DRAFT).model_copy(
        update={"applicant_fields": ApplicantFields(device_name="UPS功率模块")}
    )
    historical = detail(
        RoleCode.APPLICANT, RequirementStatus.COMPLETED, requirement_id=2
    ).model_copy(
        update={
            "applicant_fields": ApplicantFields(device_profession="电气", device_name="UPS功率模块")
        }
    )
    client.seed_requirement(current)
    client.seed_requirement(historical)
    client.purchase_records.append(
        PurchaseRecord(
            requirement_id=2,
            requirement_no="PR-2",
            device_name="UPS功率模块",
            status=RequirementStatus.COMPLETED,
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
    )

    result = await UpdatePurchaseDraftTool(client).execute(
        args=UpdatePurchaseDraftArgs(device_name="UPS功率模块"),
        context=context(
            RoleCode.APPLICANT, conversation_id=conversation.conversation_id
        ).model_copy(update={"active_requirement_id": 1}),
    )

    latest = await client.get_requirement(identity=identity(RoleCode.APPLICANT), requirement_id=1)
    assert result.status == "SUCCESS"
    assert result.updated_values["device_profession"] == "电气"
    assert latest.applicant_fields.device_profession == "电气"


@pytest.mark.asyncio
async def test_conflicting_device_profession_history_returns_ranked_recommendations() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.APPLICANT), current_action="ASSISTANT_CHAT"
    )
    current = detail(RoleCode.APPLICANT, RequirementStatus.DRAFT).model_copy(
        update={"applicant_fields": ApplicantFields(device_name="空调机组")}
    )
    client.seed_requirement(current)
    for requirement_id, profession, created_at in (
        (2, "电气", datetime(2026, 6, 1, tzinfo=UTC)),
        (3, "暖通", datetime(2026, 7, 1, tzinfo=UTC)),
        (4, "暖通", datetime(2026, 8, 1, tzinfo=UTC)),
    ):
        client.seed_requirement(
            detail(
                RoleCode.APPLICANT,
                RequirementStatus.COMPLETED,
                requirement_id=requirement_id,
            ).model_copy(
                update={
                    "applicant_fields": ApplicantFields(
                        device_profession=profession, device_name="空调机组"
                    )
                }
            )
        )
        client.purchase_records.append(
            PurchaseRecord(
                requirement_id=requirement_id,
                requirement_no=f"PR-{requirement_id}",
                device_name="空调机组",
                status=RequirementStatus.COMPLETED,
                created_at=created_at,
            )
        )

    result = await UpdatePurchaseDraftTool(client).execute(
        args=UpdatePurchaseDraftArgs(device_name="空调机组"),
        context=context(
            RoleCode.APPLICANT, conversation_id=conversation.conversation_id
        ).model_copy(update={"active_requirement_id": 1}),
    )

    assert result.status == "SUCCESS"
    assert "device_profession" not in result.updated_values
    assert result.device_profession_recommendations == ("暖通", "电气")


@pytest.mark.asyncio
async def test_start_new_draft_ignores_submitted_requirement_focus() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    client.seed_requirement(
        detail(RoleCode.APPLICANT, RequirementStatus.PENDING_REVIEW, requirement_id=1)
    )
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.APPLICANT), current_action="ASSISTANT_CHAT"
    )

    result = await UpdatePurchaseDraftTool(client).execute(
        args=UpdatePurchaseDraftArgs(
            start_new=True,
            device_profession="暖通",
            device_name="精密空调",
            quantity="2",
            unit="台",
            application_reason="机房制冷扩容",
        ),
        context=context(
            RoleCode.APPLICANT, conversation_id=conversation.conversation_id
        ).model_copy(update={"active_requirement_id": 1}),
    )

    assert result.status == "SUCCESS"
    assert result.requirement_id != 1
    assert client.call_counts["create_requirement"] == 1


@pytest.mark.asyncio
async def test_start_new_without_fields_does_not_create_empty_draft() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.APPLICANT), current_action="ASSISTANT_CHAT"
    )

    result = await UpdatePurchaseDraftTool(client).execute(
        args=UpdatePurchaseDraftArgs(start_new=True),
        context=context(RoleCode.APPLICANT, conversation_id=conversation.conversation_id),
    )

    assert result.status == "NEED_MORE_INFORMATION"
    assert client.call_counts["create_requirement"] == 0


@pytest.mark.asyncio
async def test_field_update_starts_new_draft_when_session_focus_is_submitted() -> None:
    client = FakeBackendClient(user(RoleCode.APPLICANT))
    client.seed_requirement(
        detail(RoleCode.APPLICANT, RequirementStatus.PENDING_REVIEW, requirement_id=1)
    )
    conversation = await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.APPLICANT), current_action="ASSISTANT_CHAT"
    )

    result = await UpdatePurchaseDraftTool(client).execute(
        args=UpdatePurchaseDraftArgs(
            device_profession="电气",
            device_name="UPS",
            quantity="2",
            unit="台",
        ),
        context=context(
            RoleCode.APPLICANT, conversation_id=conversation.conversation_id
        ).model_copy(update={"active_requirement_id": 1}),
    )

    assert result.status == "SUCCESS"
    assert result.requirement_id != 1
    assert result.next_missing_field == "application_reason"
    assert client.call_counts["create_requirement"] == 1


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
    client.purchase_records.append(
        PurchaseRecord(
            requirement_id=99,
            requirement_no="PR-99",
            device_name="服务器",
            brand="戴尔",
            status=RequirementStatus.COMPLETED,
            supplier_id=10,
            supplier_name="供应商A",
            purchased_at=datetime(2026, 7, 1, tzinfo=UTC),
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
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
async def test_building_manager_can_query_supplier_contact_from_backend() -> None:
    client = FakeBackendClient(user(RoleCode.BUILDING_MANAGER))
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            contract_contact_info="陈伟 13910000001",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )

    result = await QuerySupplierProfileTool(client).execute(
        args=QuerySupplierProfileArgs(
            supplier_query="供应商A",
            requested_fields=("CONTRACT_CONTACT_INFO",),
        ),
        context=context(RoleCode.BUILDING_MANAGER),
    )

    assert result.status == "SUCCESS"
    assert "陈伟 13910000001" in (result.rendered_text or "")


@pytest.mark.asyncio
async def test_supplier_profile_resolves_name_only_supplier_from_requirement() -> None:
    client = FakeBackendClient(user(RoleCode.PURCHASER))
    requirement = detail(RoleCode.PURCHASER, RequirementStatus.PURCHASING).model_copy(
        update={"review_fields": ReviewFields(proposed_supplier_name="供应商A")}
    )
    client.seed_requirement(requirement)
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            bank_name="测试银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )

    result = await QuerySupplierProfileTool(client).execute(
        args=QuerySupplierProfileArgs(
            requirement_id=1,
            requested_fields=("BANK_NAME", "BLACKLIST_STATUS"),
        ),
        context=context(RoleCode.PURCHASER),
    )

    assert result.status == "SUCCESS"
    assert result.supplier_id == 10
    assert "测试银行" in (result.rendered_text or "")
    assert client.call_counts["search_suppliers"] == 1


@pytest.mark.asyncio
async def test_supplier_profile_prefers_actual_supplier_over_review_proposal() -> None:
    client = FakeBackendClient(user(RoleCode.PURCHASER))
    requirement = detail(RoleCode.PURCHASER, RequirementStatus.PURCHASING).model_copy(
        update={
            "review_fields": ReviewFields(
                proposed_supplier_id=10,
                proposed_supplier_name="南京池润信息科技有限公司",
            ),
            "purchase_fields": PurchaseFields(supplier_id=11),
        }
    )
    client.seed_requirement(requirement)
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="南京池润信息科技有限公司",
            bank_name="南京银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
    client.seed_supplier(
        SupplierDetail(
            supplier_id=11,
            supplier_name="上海亿清",
            bank_name="上海银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )

    result = await QuerySupplierProfileTool(client).execute(
        args=QuerySupplierProfileArgs(
            requirement_id=1,
            requested_fields=("BANK_NAME",),
        ),
        context=context(RoleCode.PURCHASER),
    )

    assert result.status == "SUCCESS"
    assert result.supplier_id == 11
    assert result.supplier_name == "上海亿清"
    assert "上海银行" in (result.rendered_text or "")


@pytest.mark.asyncio
async def test_supplier_profile_uses_purchase_snapshot_name_when_id_is_stale() -> None:
    client = FakeBackendClient(user(RoleCode.PURCHASER))
    requirement = detail(RoleCode.PURCHASER, RequirementStatus.PURCHASING).model_copy(
        update={
            "review_fields": ReviewFields(
                proposed_supplier_id=10,
                proposed_supplier_name="南京池润信息科技有限公司",
            ),
            "purchase_fields": PurchaseFields(
                supplier_id=10,
                supplier_name="上海亿清",
            ),
        }
    )
    client.seed_requirement(requirement)
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="南京池润信息科技有限公司",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
    client.seed_supplier(
        SupplierDetail(
            supplier_id=11,
            supplier_name="上海亿清",
            bank_name="上海银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )

    result = await QuerySupplierProfileTool(client).execute(
        args=QuerySupplierProfileArgs(
            requirement_id=1,
            requested_fields=("BANK_NAME",),
        ),
        context=context(RoleCode.PURCHASER),
    )

    assert result.status == "SUCCESS"
    assert result.supplier_id == 11
    assert result.supplier_name == "上海亿清"


@pytest.mark.asyncio
async def test_supplier_profile_falls_back_to_purchase_record_supplier_id() -> None:
    client = FakeBackendClient(user(RoleCode.PURCHASER))
    requirement = detail(RoleCode.PURCHASER, RequirementStatus.PURCHASING).model_copy(
        update={"review_fields": None}
    )
    client.seed_requirement(requirement)
    client.purchase_records.append(
        PurchaseRecord(
            requirement_id=1,
            requirement_no="PR-1",
            device_name="服务器",
            status=RequirementStatus.PURCHASING,
            supplier_id=10,
            supplier_name="供应商A",
            created_at=datetime(2026, 8, 3, tzinfo=UTC),
        )
    )
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            bank_name="测试银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )

    result = await QuerySupplierProfileTool(client).execute(
        args=QuerySupplierProfileArgs(
            requirement_id=1,
            requested_fields=("BANK_NAME",),
        ),
        context=context(RoleCode.PURCHASER),
    )

    assert result.status == "SUCCESS"
    assert result.supplier_id == 10
    assert client.call_counts["list_purchase_records"] == 1
    assert client.call_counts["search_suppliers"] == 0


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
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            supplier_tax_number="91310000TEST",
            bank_name="测试银行",
            bank_account="TEST-ACCOUNT",
            registered_address="测试地址",
            contract_contact_info="陈伟 13910000001",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
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
    saved = client._requirements[1].purchase_fields
    assert saved is not None
    assert saved.supplier_tax_number == "91310000TEST"
    assert saved.bank_name == "测试银行"
    assert client.call_counts["submit_warehouse"] == 0


@pytest.mark.asyncio
async def test_fill_selected_supplier_profile_reloads_master_and_asks_for_unit_price() -> None:
    client = FakeBackendClient(user(RoleCode.PURCHASER))
    await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.PURCHASER), current_action="ASSISTANT_CHAT"
    )
    client.seed_requirement(detail(RoleCode.PURCHASER, RequirementStatus.PURCHASING))
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            bank_name="测试银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )

    result = await FillSelectedSupplierProfileTool(client).execute(
        args=FillSelectedSupplierProfileArgs(requirement_id=1),
        context=context(RoleCode.PURCHASER),
    )

    assert result.status == "NEED_MORE_INFORMATION"
    assert result.supplier_name == "供应商A"
    assert result.next_missing_field == "actual_unit_price"
    assert "将在采购执行信息完整后一起保存" in (result.user_message or "")
    assert client.call_counts["get_supplier"] == 1
    assert client.call_counts["update_purchase_fields"] == 0


@pytest.mark.asyncio
async def test_purchase_execution_resolves_legacy_name_only_selected_supplier() -> None:
    client = FakeBackendClient(user(RoleCode.PURCHASER))
    requirement = detail(RoleCode.PURCHASER, RequirementStatus.PURCHASING).model_copy(
        update={"review_fields": ReviewFields(proposed_supplier_name="供应商A")}
    )
    client.seed_requirement(requirement)
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            bank_name="测试银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )

    result = await UpdatePurchaseExecutionDraftTool(client).execute(
        args=UpdatePurchaseExecutionDraftArgs(
            requirement_id=1,
            actual_unit_price="10",
            purchased_at=datetime(2026, 8, 3, tzinfo=UTC),
        ),
        context=context(RoleCode.PURCHASER),
    )

    assert result.status == "SUCCESS"
    assert client.call_counts["search_suppliers"] == 1
    assert client._requirements[1].purchase_fields is not None
    assert client._requirements[1].purchase_fields.supplier_id == 10


@pytest.mark.asyncio
async def test_purchase_execution_uses_system_time_when_price_is_provided() -> None:
    client = FakeBackendClient(user(RoleCode.PURCHASER))
    await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.PURCHASER), current_action="ASSISTANT_CHAT"
    )
    client.seed_requirement(detail(RoleCode.PURCHASER, RequirementStatus.PURCHASING))
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            bank_name="测试银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
    tool = UpdatePurchaseExecutionDraftTool(client)

    price = await tool.execute(
        args=UpdatePurchaseExecutionDraftArgs(requirement_id=1, actual_unit_price="10.25"),
        context=context(RoleCode.PURCHASER),
    )
    assert price.status == "SUCCESS"
    assert price.actual_total_price == "20.50"
    saved = client._requirements[1].purchase_fields
    assert saved is not None
    assert saved.purchased_at == context(RoleCode.PURCHASER).current_time
    assert client.call_counts["update_purchase_fields"] == 1


@pytest.mark.asyncio
async def test_purchaser_pending_unit_price_reply_bypasses_llm_and_returns_card() -> None:
    client = FakeBackendClient(user(RoleCode.PURCHASER))
    await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.PURCHASER), current_action="ASSISTANT_CHAT"
    )
    client.seed_requirement(detail(RoleCode.PURCHASER, RequirementStatus.PURCHASING))
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            bank_name="测试银行",
            bank_account="TEST-ACCT-00000001",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
    fill_tool = FillSelectedSupplierProfileTool(client)
    update_tool = UpdatePurchaseExecutionDraftTool(client)
    registry = ToolRegistry()
    registry.register(QuerySupplierProfileTool(client))
    registry.register(FillSelectedSupplierProfileTool(client))
    registry.register(update_tool)
    executor = ToolExecutor(registry, max_result_chars=10_000)
    agent = PurchaserAgent(AssistantSessionService(client), executor, client)
    await fill_tool.execute(
        args=FillSelectedSupplierProfileArgs(requirement_id=1),
        context=context(RoleCode.PURCHASER),
    )

    response = await agent.before_run(
        context=context(RoleCode.PURCHASER),
        history=(),
        user_text="16500",
        external_message_id="om-price",
    )

    assert isinstance(response, AssistantInteractionResponse)
    assert response.view.title == "采购员采购执行"
    assert response.view.actions
    bank_account_input = next(
        element
        for element in response.view.elements
        if getattr(element, "name", None) == "bank_account"
    )
    assert bank_account_input.default_value == "TEST-ACCT-00000001"
    state = await client.get_agent_state(identity=identity(RoleCode.PURCHASER), conversation_id=1)
    assert state.pending_field is None
    assert client._requirements[1].purchase_fields is not None
    assert client._requirements[1].purchase_fields.actual_unit_price == "16500"
    assert client._requirements[1].purchase_fields.bank_account == "TEST-ACCT-00000001"
    assert (
        client._requirements[1].purchase_fields.purchased_at
        == context(RoleCode.PURCHASER).current_time
    )
    assert client.call_counts["update_purchase_fields"] == 1


@pytest.mark.asyncio
async def test_purchaser_open_requirement_number_returns_formal_card_without_llm() -> None:
    client = FakeBackendClient(user(RoleCode.PURCHASER))
    await client.get_or_create_agent_conversation(
        identity=identity(RoleCode.PURCHASER), current_action="ASSISTANT_CHAT"
    )
    requirement = detail(
        RoleCode.PURCHASER, RequirementStatus.PURCHASING, requirement_id=91092
    ).model_copy(update={"requirement_no": "PR-20260810-5132E77E"})
    client.seed_requirement(requirement)
    client.seed_supplier(
        SupplierDetail(
            supplier_id=10,
            supplier_name="供应商A",
            bank_name="测试银行",
            blacklist=SupplierBlacklistSummary(active=False),
        )
    )
    client.purchase_records.append(
        PurchaseRecord(
            requirement_id=91092,
            requirement_no="PR-20260810-5132E77E",
            device_name="UPS功率模块",
            status=RequirementStatus.PURCHASING,
            created_at=datetime(2026, 8, 10, tzinfo=UTC),
        )
    )
    registry = ToolRegistry()
    registry.register(QuerySupplierProfileTool(client))
    registry.register(FillSelectedSupplierProfileTool(client))
    agent = PurchaserAgent(
        AssistantSessionService(client),
        ToolExecutor(registry, max_result_chars=10_000),
        client,
    )

    response = await agent.before_run(
        context=context(RoleCode.PURCHASER),
        history=(),
        user_text="打开 PR-20260810-5132E77E 采购单",
        external_message_id="om-open",
    )

    assert isinstance(response, AssistantInteractionResponse)
    assert response.view.title == "采购员采购执行"
    assert client.call_counts["list_purchase_records"] == 1
    assert client.call_counts["get_requirement"] == 1
    state = await client.get_agent_state(identity=identity(RoleCode.PURCHASER), conversation_id=1)
    assert state.purchase_request_id == 91092

    supplier_response = await agent.before_run(
        context=context(RoleCode.PURCHASER),
        history=(),
        user_text="这个采购单供应商的信息",
        external_message_id="om-supplier-info",
    )
    fill_response = await agent.before_run(
        context=context(RoleCode.PURCHASER),
        history=(),
        user_text="帮这些信息填入采购单",
        external_message_id="om-fill-supplier",
    )

    assert supplier_response is not None
    assert getattr(supplier_response, "text", "").find("测试银行") >= 0
    assert fill_response is not None
    assert getattr(fill_response, "text", "").find("实际采购单价") >= 0
    assert client.call_counts["list_purchase_records"] == 1


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
