from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ConfigDict

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.assistant.capabilities import (
    DEFAULT_CAPABILITY_METADATA,
    CapabilityMetadata,
    CapabilityPolicy,
    CapabilityRegistry,
    ExistingToolCapabilityAdapter,
)
from procurement_platform.application.assistant.capabilities.registry import (
    DuplicateCapabilityError,
    UnknownCapabilityError,
)
from procurement_platform.application.assistant.capabilities.requirements import (
    GetPurchaseRequestResult,
    GetPurchaseTimelineResult,
    SearchPurchaseRequestsArgs,
    SearchPurchaseRequestsResult,
)
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.bootstrap.container import _build_capability_registry
from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser, UserRole


class ExampleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


class ExampleTool:
    name = "example"
    description = "Example capability."
    side_effect = "READ"
    args_model = ExampleArgs

    async def execute(
        self, *, args: ExampleArgs, context: AssistantToolContext
    ) -> AssistantToolResult:
        del context
        return AssistantToolResult(status="SUCCESS", user_message=args.value)


def _user(*roles: RoleCode, status: str = "ACTIVE") -> CurrentUser:
    return CurrentUser(
        employee_id=1,
        name="Capability Test",
        mobile=None,
        status=status,
        roles=tuple(UserRole(role_code=role) for role in roles),
        buildings=(),
    )


def _example_capability() -> ExistingToolCapabilityAdapter[ExampleArgs, AssistantToolResult]:
    return ExistingToolCapabilityAdapter(
        ExampleTool(),
        CapabilityMetadata(
            name="example",
            description="Example capability.",
            side_effect="READ",
            allowed_roles=frozenset({RoleCode.APPLICANT}),
        ),
    )


def test_registry_registers_gets_and_lists_capabilities_in_stable_order() -> None:
    registry = CapabilityRegistry()
    capability = _example_capability()

    registry.register(capability)

    assert registry.get("example").name == capability.name
    assert tuple(item.name for item in registry.all()) == ("example",)
    assert registry.names() == ("example",)
    assert registry.tool_registry.registered_names == frozenset({"example"})


def test_registry_rejects_duplicate_and_unknown_capabilities() -> None:
    registry = CapabilityRegistry()
    registry.register(_example_capability())

    with pytest.raises(DuplicateCapabilityError):
        registry.register(_example_capability())
    with pytest.raises(UnknownCapabilityError):
        registry.get("missing")


def test_adapter_reuses_existing_tool_contract() -> None:
    capability = _example_capability()

    assert capability.name == ExampleTool.name
    assert capability.description == ExampleTool.description
    assert capability.args_model is ExampleArgs
    assert capability.side_effect == "READ"


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (
            RoleCode.APPLICANT,
            {
                "search_purchase_requests",
                "get_purchase_request",
                "get_purchase_timeline",
                "recommend_products",
                "update_applicant_draft",
                "diagnose_procurement_need",
                "find_similar_purchases",
                "compare_products",
            },
        ),
        (
            RoleCode.BUILDING_MANAGER,
            {
                "search_purchase_requests",
                "get_purchase_request",
                "get_purchase_timeline",
                "get_supplier_profile",
                "recommend_suppliers",
                "update_review_draft",
                "find_similar_purchases",
                "compare_products",
                "compare_suppliers",
            },
        ),
        (
            RoleCode.PURCHASER,
            {
                "search_purchase_requests",
                "get_purchase_request",
                "get_purchase_timeline",
                "get_supplier_profile",
                "prepare_purchase_prefill",
                "apply_supplier_profile_to_draft",
                "update_purchase_draft",
                "find_similar_purchases",
                "compare_products",
                "compare_suppliers",
            },
        ),
        (
            RoleCode.WAREHOUSE_MANAGER,
            {
                "search_purchase_requests",
                "get_purchase_request",
                "get_purchase_timeline",
                "update_warehouse_draft",
                "find_similar_purchases",
            },
        ),
    ],
)
def test_single_role_permissions_remain_compatible(role: RoleCode, expected: set[str]) -> None:
    policy = CapabilityPolicy(DEFAULT_CAPABILITY_METADATA)
    user = _user(role)

    expected.update(
        {
            "search_assets",
            "resolve_asset",
            "get_asset",
            "get_asset_components",
            "get_asset_relations",
        }
    )
    assert policy.allowed_names_for(user) == frozenset(expected)
    assert ToolPolicy(policy).allowed_tool_names(current_user=user, active_role=role) == frozenset(
        expected
    )


def test_policy_unions_capabilities_for_multi_role_user() -> None:
    policy = CapabilityPolicy(DEFAULT_CAPABILITY_METADATA)

    actual = policy.allowed_names_for(_user(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER))

    assert actual == frozenset(
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


def test_policy_rejects_inactive_user_and_catalog_excludes_formal_actions() -> None:
    policy = CapabilityPolicy(DEFAULT_CAPABILITY_METADATA)

    assert policy.allowed_names_for(_user(RoleCode.APPLICANT, status="INACTIVE")) == frozenset()
    assert not {item.name for item in DEFAULT_CAPABILITY_METADATA}.intersection(
        {
            "submit_review",
            "reject",
            "resubmit_review",
            "submit_purchaser",
            "start_purchase",
            "submit_warehouse",
            "complete",
        }
    )


@pytest.mark.asyncio
async def test_role_policy_registry_existing_tool_fake_backend_chain() -> None:
    user = _user(RoleCode.APPLICANT)
    registry = _build_capability_registry(FakeBackendClient(user))
    policy = CapabilityPolicy(registry)
    capability = registry.get("search_purchase_requests")
    context = AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id="ou_capability_test",
        conversation_id=1,
        external_conversation_id="oc_capability_test",
        external_message_id="om_capability_test",
        current_time=datetime(2026, 8, 15, tzinfo=UTC),
        timezone_name="Asia/Shanghai",
        current_user=user,
        active_requirement_id=None,
    )

    result = await capability.execute(args=SearchPurchaseRequestsArgs(), context=context)

    assert "search_purchase_requests" in policy.allowed_names_for(user)
    assert result.status == "NOT_FOUND"
    assert registry.names() == tuple(item.name for item in DEFAULT_CAPABILITY_METADATA)


def test_requirement_v2_schemas_have_no_operation_router() -> None:
    registry = _build_capability_registry(FakeBackendClient(_user(RoleCode.APPLICANT)))

    for name in (
        "search_purchase_requests",
        "get_purchase_request",
        "get_purchase_timeline",
    ):
        capability = registry.get(name)
        assert "operation" not in capability.args_model.model_json_schema()["properties"]
        assert "Do not" in capability.description or "do not" in capability.description

    assert "query_purchase_requests" not in registry.names()


@pytest.mark.asyncio
async def test_requirement_v2_returns_action_specific_typed_results() -> None:
    user = _user(RoleCode.APPLICANT)
    backend = FakeBackendClient(user)
    registry = _build_capability_registry(backend)
    context = AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id="ou_capability_results",
        conversation_id=1,
        external_conversation_id="oc_capability_results",
        external_message_id="om_capability_results",
        current_time=datetime(2026, 8, 15, tzinfo=UTC),
        timezone_name="Asia/Shanghai",
        current_user=user,
        active_requirement_id=None,
    )

    search = await registry.get("search_purchase_requests").execute(
        args=SearchPurchaseRequestsArgs(), context=context
    )
    detail = await registry.get("get_purchase_request").execute(
        args=registry.get("get_purchase_request").args_model(requirement_id=999),
        context=context,
    )
    timeline = await registry.get("get_purchase_timeline").execute(
        args=registry.get("get_purchase_timeline").args_model(requirement_id=999),
        context=context,
    )

    assert isinstance(search, SearchPurchaseRequestsResult)
    assert isinstance(detail, GetPurchaseRequestResult)
    assert isinstance(timeline, GetPurchaseTimelineResult)
