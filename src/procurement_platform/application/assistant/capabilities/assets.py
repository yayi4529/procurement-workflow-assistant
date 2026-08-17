import re
from typing import Literal

from pydantic import Field

from procurement_platform.application.assistant.entity_references import (
    asset_reference,
    model_reference,
    parse_asset_reference,
)
from procurement_platform.application.assistant.tooling.common import StrictArgs
from procurement_platform.domain.assets import AssetContext, AssetSummary
from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.ports.backend_client import BackendClient


def _identity(context: AssistantToolContext) -> PlatformIdentity:
    return PlatformIdentity.create(PlatformType(context.platform_type), context.platform_user_id)


def _normalize(value: str) -> str:
    return re.sub(r"[\s#\uFF03号\-_]", "", value).casefold()


class AssetFact(StrictArgs):
    asset_ref: str
    asset_code: str
    asset_name: str
    category_code: str
    category_name: str
    model_ref: str | None = None
    brand: str | None = None
    model: str | None = None
    building_id: int
    building_name: str
    location: str | None
    status: str
    criticality: str


def _fact(asset: AssetSummary) -> AssetFact:
    return AssetFact(
        asset_ref=asset_reference(asset.asset_id),
        asset_code=asset.asset_code,
        asset_name=asset.asset_name,
        category_code=asset.category.category_code,
        category_name=asset.category.category_name,
        model_ref=model_reference(asset.model.model_id) if asset.model is not None else None,
        brand=asset.model.brand if asset.model is not None else None,
        model=asset.model.model if asset.model is not None else None,
        building_id=asset.building_id,
        building_name=asset.building.building_name,
        location=asset.location,
        status=asset.status,
        criticality=asset.criticality,
    )


class SearchAssetsArgs(StrictArgs):
    query: str | None = Field(default=None, max_length=250)
    building_id: int | None = Field(default=None, gt=0)
    category_code: str | None = Field(default=None, max_length=50)
    model_ref: str | None = Field(default=None, max_length=80)
    status: str | None = "ACTIVE"
    limit: int = Field(default=10, ge=1, le=20)


class SearchAssetsResult(AssistantToolResult):
    items: tuple[AssetFact, ...] = ()
    total_count: int = 0


class SearchAssetsCapability:
    name = "search_assets"
    side_effect = "READ"
    description = (
        "Search authoritative data-center assets by text, building, category, model, "
        "or status. Read-only."
    )
    args_model = SearchAssetsArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def execute(
        self, *, args: SearchAssetsArgs, context: AssistantToolContext
    ) -> SearchAssetsResult:
        model_id = None
        if args.model_ref is not None:
            prefix, _, raw = args.model_ref.partition(":")
            if prefix != "model" or not raw.isdecimal() or int(raw) <= 0:
                return SearchAssetsResult(status="INVALID_ARGUMENTS", user_message="型号引用无效")
            model_id = int(raw)
        page = await self._backend.search_assets(
            identity=_identity(context),
            building_id=args.building_id,
            category_code=args.category_code,
            model_id=model_id,
            status=args.status,
            query=args.query,
            page_size=args.limit,
        )
        return SearchAssetsResult(
            status="SUCCESS",
            items=tuple(_fact(item) for item in page.items),
            total_count=page.total,
            user_message="未找到匹配资产" if not page.items else None,
        )


class ResolveAssetArgs(StrictArgs):
    phrase: str = Field(min_length=1, max_length=250)
    building_id: int | None = Field(default=None, gt=0)
    category_code: str | None = Field(default=None, max_length=50)


class ResolveAssetResult(AssistantToolResult):
    resolution: Literal["RESOLVED", "AMBIGUOUS", "NOT_FOUND"]
    asset: AssetFact | None = None
    candidates: tuple[AssetFact, ...] = ()


class AssetResolver:
    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def resolve(
        self, *, args: ResolveAssetArgs, context: AssistantToolContext
    ) -> ResolveAssetResult:
        page = await self._backend.search_assets(
            identity=_identity(context),
            building_id=args.building_id,
            category_code=args.category_code,
            status=None,
            query=args.phrase,
            page_size=100,
        )
        needle = _normalize(args.phrase)
        exact_code = [item for item in page.items if _normalize(item.asset_code) == needle]
        exact_name = [item for item in page.items if _normalize(item.asset_name) == needle]
        exact_alias = [
            item for item in page.items if needle in {_normalize(alias) for alias in item.aliases}
        ]
        candidates = exact_code or exact_name or exact_alias or list(page.items)
        if not candidates:
            return ResolveAssetResult(
                status="NOT_FOUND", resolution="NOT_FOUND", user_message="未找到匹配资产"
            )
        if len(candidates) > 1:
            return ResolveAssetResult(
                status="MULTIPLE_MATCHES",
                resolution="AMBIGUOUS",
                candidates=tuple(_fact(item) for item in candidates[:10]),
                user_message="匹配到多个资产; 请补充楼宇、位置或资产编号",
            )
        return ResolveAssetResult(
            status="SUCCESS", resolution="RESOLVED", asset=_fact(candidates[0])
        )


class ResolveAssetCapability:
    name = "resolve_asset"
    side_effect = "READ"
    description = (
        "Resolve a natural-language asset phrase deterministically; returns one asset, "
        "candidates, or not found and never guesses ambiguity. Read-only."
    )
    args_model = ResolveAssetArgs

    def __init__(self, backend: BackendClient) -> None:
        self._resolver = AssetResolver(backend)

    async def execute(
        self, *, args: ResolveAssetArgs, context: AssistantToolContext
    ) -> ResolveAssetResult:
        return await self._resolver.resolve(args=args, context=context)


class AssetRefArgs(StrictArgs):
    asset_ref: str = Field(min_length=7, max_length=80)


class GetAssetResult(AssistantToolResult):
    asset: AssetFact | None = None
    specifications: dict[str, object] | None = None
    configuration: dict[str, object] | None = None
    commissioned_at: str | None = None
    warranty_end_at: str | None = None
    missing_facts: tuple[str, ...] = ()


class GetAssetCapability:
    name = "get_asset"
    side_effect = "READ"
    description = (
        "Get authoritative asset, category, model, location, lifecycle dates, "
        "specifications and configuration by stable asset ref. Read-only."
    )
    args_model = AssetRefArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def execute(self, *, args: AssetRefArgs, context: AssistantToolContext) -> GetAssetResult:
        try:
            asset_id = parse_asset_reference(args.asset_ref)
        except ValueError:
            return GetAssetResult(status="INVALID_ARGUMENTS", user_message="资产引用无效")
        asset = await self._backend.get_asset(identity=_identity(context), asset_id=asset_id)
        missing = []
        if asset.model is None:
            missing.append("model")
        if asset.commissioned_at is None:
            missing.append("commissioned_at")
        if asset.warranty_end_at is None:
            missing.append("warranty_end_at")
        return GetAssetResult(
            status="SUCCESS",
            asset=_fact(asset),
            specifications=asset.model.specifications if asset.model else None,
            configuration=asset.configuration,
            commissioned_at=asset.commissioned_at.isoformat() if asset.commissioned_at else None,
            warranty_end_at=asset.warranty_end_at.isoformat() if asset.warranty_end_at else None,
            missing_facts=tuple(missing),
            user_message="当前资产档案中未登记具体型号" if "model" in missing else None,
        )


class ComponentFact(StrictArgs):
    component_name: str
    component_category: str | None
    brand: str | None
    model_or_part_no: str | None
    quantity: str
    unit: str | None
    status: str
    replaceable: bool


class GetAssetComponentsResult(AssistantToolResult):
    asset_ref: str | None = None
    components: tuple[ComponentFact, ...] = ()
    data_scope: str = "主要部件; 不是完整 BOM"


class GetAssetComponentsCapability:
    name = "get_asset_components"
    side_effect = "READ"
    description = (
        "Get only the registered coarse major components for an asset from one "
        "authoritative context read. Never invents a BOM. Read-only."
    )
    args_model = AssetRefArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def execute(
        self, *, args: AssetRefArgs, context: AssistantToolContext
    ) -> GetAssetComponentsResult:
        try:
            asset_id = parse_asset_reference(args.asset_ref)
        except ValueError:
            return GetAssetComponentsResult(status="INVALID_ARGUMENTS", user_message="资产引用无效")
        data = await self._backend.get_asset_context(identity=_identity(context), asset_id=asset_id)
        items = tuple(
            ComponentFact(
                component_name=item.component_name,
                component_category=item.component_category,
                brand=item.brand,
                model_or_part_no=item.model_or_part_no,
                quantity=str(item.quantity),
                unit=item.unit,
                status=item.status,
                replaceable=item.replaceable,
            )
            for item in data.components
        )
        return GetAssetComponentsResult(
            status="SUCCESS",
            asset_ref=args.asset_ref,
            components=items,
            user_message="当前资产档案没有登记主要部件" if not items else None,
        )


class RelationFact(StrictArgs):
    relation_type: str
    direction: str
    related_asset_ref: str
    related_asset_code: str
    related_asset_name: str
    remark: str | None


class GetAssetRelationsResult(AssistantToolResult):
    asset_ref: str | None = None
    relations: tuple[RelationFact, ...] = ()
    redundancy_peers: tuple[AssetFact, ...] = ()


class GetAssetRelationsCapability:
    name = "get_asset_relations"
    side_effect = "READ"
    description = (
        "Get registered asset relationships and same-redundancy-group peers from one "
        "authoritative context read. Never infers missing topology. Read-only."
    )
    args_model = AssetRefArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def execute(
        self, *, args: AssetRefArgs, context: AssistantToolContext
    ) -> GetAssetRelationsResult:
        try:
            asset_id = parse_asset_reference(args.asset_ref)
        except ValueError:
            return GetAssetRelationsResult(status="INVALID_ARGUMENTS", user_message="资产引用无效")
        data: AssetContext = await self._backend.get_asset_context(
            identity=_identity(context), asset_id=asset_id
        )
        relations = tuple(
            RelationFact(
                relation_type=item.relation_type,
                direction=item.direction,
                related_asset_ref=asset_reference(item.related_asset.asset_id),
                related_asset_code=item.related_asset.asset_code,
                related_asset_name=item.related_asset.asset_name,
                remark=item.remark,
            )
            for item in data.relations
        )
        return GetAssetRelationsResult(
            status="SUCCESS",
            asset_ref=args.asset_ref,
            relations=relations,
            redundancy_peers=tuple(_fact(item) for item in data.redundancy_peers),
            user_message="当前资产档案未登记该关系" if not relations else None,
        )
