from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.assistant.capabilities.assets import (
    AssetRefArgs,
    GetAssetCapability,
    GetAssetComponentsCapability,
    GetAssetRelationsCapability,
    ResolveAssetArgs,
    ResolveAssetCapability,
    SearchAssetsArgs,
    SearchAssetsCapability,
)
from procurement_platform.application.assistant.entity_references import (
    asset_reference,
    model_reference,
    parse_asset_reference,
)
from procurement_platform.domain.assets import (
    AssetComponent,
    AssetContext,
    AssetRelation,
    AssetSummary,
    BuildingSummary,
    EquipmentCategorySummary,
    EquipmentModelSummary,
    RelatedAsset,
)
from procurement_platform.domain.assistant import AssistantToolContext
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def user() -> CurrentUser:
    return CurrentUser(
        employee_id=1,
        name="测试用户",
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=RoleCode.APPLICANT, role_name="需求人"),),
        buildings=(
            UserBuilding(building_id=1, building_name="一号楼", is_primary=True),
            UserBuilding(building_id=2, building_name="二号楼", is_primary=False),
        ),
    )


def tool_context() -> AssistantToolContext:
    return AssistantToolContext(
        platform_type="TEST_PLATFORM",
        platform_user_id="test-user",
        conversation_id=1,
        external_conversation_id="c1",
        external_message_id="m1",
        current_time=datetime.now(UTC),
        timezone_name="Asia/Shanghai",
        current_user=user(),
    )


def asset(asset_id: int, building_id: int, *, with_model: bool = True) -> AssetSummary:
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
    model = (
        EquipmentModelSummary(
            model_id=20,
            category_id=10,
            brand="TEST",
            model="UPS-500",
            model_name=None,
            specifications={"capacity_kva": 500},
            default_unit="台",
            lifecycle_status="ACTIVE",
            remark=None,
        )
        if with_model
        else None
    )
    return AssetSummary(
        asset_id=asset_id,
        asset_code=f"TEST-UPS-{building_id}",
        asset_name=f"{building_id}号楼二层2号UPS",
        category_id=10,
        model_id=model.model_id if model else None,
        building_id=building_id,
        location="二层UPS室",
        serial_number=None,
        status="ACTIVE",
        criticality="CRITICAL",
        commissioned_at=date(2025, 1, 1),
        warranty_end_at=None,
        configuration={"installed_module_count": 8},
        aliases=("2号UPS", "UPS02"),
        redundancy_group=None,
        redundancy_mode=None,
        remark=None,
        version=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        category=category,
        model=model,
        building=BuildingSummary(building_id=building_id, building_name=f"{building_id}号楼"),
    )


def context(value: AssetSummary, *, include_facts: bool = True) -> AssetContext:
    components = (
        (
            AssetComponent(
                component_id=1,
                asset_id=value.asset_id,
                component_name="功率模块",
                component_category="POWER_MODULE",
                brand=None,
                model_or_part_no=None,
                quantity=Decimal("8"),
                unit="块",
                status="NORMAL",
                replaceable=True,
                remark=None,
            ),
        )
        if include_facts
        else ()
    )
    relations = (
        (
            AssetRelation(
                relation_id=1,
                source_asset_id=value.asset_id,
                relation_type="CONNECTED_TO",
                target_asset_id=99,
                remark=None,
                status="ACTIVE",
                direction="OUTGOING",
                related_asset=RelatedAsset(
                    asset_id=99,
                    asset_code="TEST-BAT-1",
                    asset_name="测试电池组",
                    building_id=value.building_id,
                    location=None,
                    status="ACTIVE",
                ),
            ),
        )
        if include_facts
        else ()
    )
    return AssetContext(
        asset=value, components=components, relations=relations, redundancy_peers=()
    )


def fake() -> FakeBackendClient:
    backend = FakeBackendClient(user())
    backend.seed_asset_context(context(asset(1, 1)))
    backend.seed_asset_context(context(asset(2, 2, with_model=False), include_facts=False))
    return backend


def test_stable_asset_and_model_references_use_backend_ids() -> None:
    assert asset_reference(108) == "asset:108"
    assert model_reference(25) == "model:25"
    assert parse_asset_reference("asset:108") == 108
    with pytest.raises(ValueError):
        parse_asset_reference("asset:guess")


@pytest.mark.asyncio
async def test_resolver_does_not_guess_same_alias_in_two_buildings() -> None:
    backend = fake()
    result = await ResolveAssetCapability(backend).execute(
        args=ResolveAssetArgs(phrase="2号UPS"), context=tool_context()
    )
    assert result.status == "MULTIPLE_MATCHES"
    assert result.resolution == "AMBIGUOUS"
    assert {item.asset_ref for item in result.candidates} == {"asset:1", "asset:2"}


@pytest.mark.asyncio
async def test_resolver_exact_code_and_building_filter_are_deterministic() -> None:
    backend = fake()
    by_code = await ResolveAssetCapability(backend).execute(
        args=ResolveAssetArgs(phrase="TEST-UPS-1"), context=tool_context()
    )
    by_building = await ResolveAssetCapability(backend).execute(
        args=ResolveAssetArgs(phrase="2号UPS", building_id=2), context=tool_context()
    )
    assert by_code.asset and by_code.asset.asset_ref == "asset:1"
    assert by_building.asset and by_building.asset.asset_ref == "asset:2"


@pytest.mark.asyncio
async def test_asset_capabilities_are_grounded_and_context_reads_are_single_call() -> None:
    backend = fake()
    search = await SearchAssetsCapability(backend).execute(
        args=SearchAssetsArgs(category_code="UPS"), context=tool_context()
    )
    detail = await GetAssetCapability(backend).execute(
        args=AssetRefArgs(asset_ref="asset:2"), context=tool_context()
    )
    components = await GetAssetComponentsCapability(backend).execute(
        args=AssetRefArgs(asset_ref="asset:2"), context=tool_context()
    )
    relations = await GetAssetRelationsCapability(backend).execute(
        args=AssetRefArgs(asset_ref="asset:2"), context=tool_context()
    )
    assert search.total_count == 2
    assert detail.asset and detail.asset.model is None
    assert "model" in detail.missing_facts
    assert detail.user_message == "当前资产档案中未登记具体型号"
    assert components.components == ()
    assert components.user_message == "当前资产档案没有登记主要部件"
    assert relations.relations == ()
    assert relations.user_message == "当前资产档案未登记该关系"
    assert backend.call_counts["get_asset_context"] == 2
    assert all(
        tool.side_effect == "READ"
        for tool in (
            SearchAssetsCapability,
            ResolveAssetCapability,
            GetAssetCapability,
            GetAssetComponentsCapability,
            GetAssetRelationsCapability,
        )
    )
