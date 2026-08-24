from typing import Protocol

from procurement_platform.application.assistant.capabilities.analytics import (
    DescribeAnalyticsSchemaCapability,
    RunReadonlyAnalyticsSqlCapability,
)
from procurement_platform.application.assistant.capabilities.assets import (
    GetAssetCapability,
    GetAssetComponentsCapability,
    GetAssetRelationsCapability,
    ResolveAssetCapability,
    SearchAssetsCapability,
)
from procurement_platform.application.assistant.capabilities.drafts import (
    UpdateMultiItemDraftCapability,
    UpdateReviewDraftCapability,
)
from procurement_platform.application.assistant.capabilities.intelligence import (
    CompareProductsCapability,
    CompareSuppliersCapability,
    DiagnoseProcurementNeedCapability,
    FindSimilarPurchasesCapability,
)
from procurement_platform.application.assistant.capabilities.metadata import CapabilityMetadata
from procurement_platform.application.assistant.capabilities.products.recommend import (
    RecommendProductsByNameCapability,
)
from procurement_platform.application.assistant.capabilities.purchases import (
    PreparePurchasePrefillCapability,
)
from procurement_platform.application.assistant.capabilities.skill_handlers import (
    ProcurementAnalyticsHandler,
    SupplierRecommendationHandler,
)
from procurement_platform.application.assistant.capabilities.v2 import (
    ApplySupplierProfileCapability,
    GetPurchaseRequestCapability,
    GetPurchaseTimelineCapability,
    GetSupplierProfileCapability,
    RecommendProductsCapability,
    RecommendSuppliersCapability,
    SearchPurchaseRequestsCapability,
    UpdateApplicantDraftCapability,
    UpdatePurchaseDraftCapability,
    UpdateWarehouseDraftCapability,
)
from procurement_platform.application.assistant.tools import ToolSideEffect
from procurement_platform.domain.enums import RoleCode

ALL_WORKFLOW_ROLES = frozenset(
    {
        RoleCode.APPLICANT,
        RoleCode.BUILDING_MANAGER,
        RoleCode.PURCHASER,
        RoleCode.WAREHOUSE_MANAGER,
    }
)


class _ToolDescriptor(Protocol):
    name: str
    description: str
    side_effect: ToolSideEffect


def _metadata(
    tool_type: type[_ToolDescriptor], allowed_roles: frozenset[RoleCode]
) -> CapabilityMetadata:
    return CapabilityMetadata(
        name=tool_type.name,
        description=tool_type.description,
        side_effect=tool_type.side_effect,
        allowed_roles=allowed_roles,
    )


DEFAULT_CAPABILITY_METADATA: tuple[CapabilityMetadata, ...] = (
    _metadata(
        ProcurementAnalyticsHandler,
        frozenset({RoleCode.PURCHASER, RoleCode.ADMIN}),
    ),
    _metadata(
        SupplierRecommendationHandler,
        frozenset({RoleCode.PURCHASER, RoleCode.ADMIN}),
    ),
    _metadata(
        DescribeAnalyticsSchemaCapability,
        frozenset({RoleCode.PURCHASER, RoleCode.ADMIN}),
    ),
    _metadata(
        RunReadonlyAnalyticsSqlCapability,
        frozenset({RoleCode.PURCHASER, RoleCode.ADMIN}),
    ),
    _metadata(SearchAssetsCapability, ALL_WORKFLOW_ROLES),
    _metadata(ResolveAssetCapability, ALL_WORKFLOW_ROLES),
    _metadata(GetAssetCapability, ALL_WORKFLOW_ROLES),
    _metadata(GetAssetComponentsCapability, ALL_WORKFLOW_ROLES),
    _metadata(GetAssetRelationsCapability, ALL_WORKFLOW_ROLES),
    _metadata(DiagnoseProcurementNeedCapability, frozenset({RoleCode.APPLICANT})),
    _metadata(FindSimilarPurchasesCapability, ALL_WORKFLOW_ROLES),
    _metadata(RecommendProductsByNameCapability, ALL_WORKFLOW_ROLES),
    _metadata(
        CompareProductsCapability,
        frozenset({RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER, RoleCode.PURCHASER}),
    ),
    _metadata(
        CompareSuppliersCapability,
        frozenset({RoleCode.BUILDING_MANAGER, RoleCode.PURCHASER}),
    ),
    _metadata(SearchPurchaseRequestsCapability, ALL_WORKFLOW_ROLES),
    _metadata(GetPurchaseRequestCapability, ALL_WORKFLOW_ROLES),
    _metadata(GetPurchaseTimelineCapability, ALL_WORKFLOW_ROLES),
    _metadata(
        RecommendProductsCapability,
        frozenset({RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER, RoleCode.PURCHASER}),
    ),
    _metadata(UpdateApplicantDraftCapability, frozenset({RoleCode.APPLICANT})),
    _metadata(UpdateMultiItemDraftCapability, frozenset({RoleCode.APPLICANT})),
    _metadata(
        RecommendSuppliersCapability,
        frozenset({RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER, RoleCode.PURCHASER}),
    ),
    _metadata(UpdateReviewDraftCapability, frozenset({RoleCode.BUILDING_MANAGER})),
    _metadata(
        GetSupplierProfileCapability,
        frozenset({RoleCode.BUILDING_MANAGER, RoleCode.PURCHASER}),
    ),
    _metadata(PreparePurchasePrefillCapability, frozenset({RoleCode.PURCHASER})),
    _metadata(ApplySupplierProfileCapability, frozenset({RoleCode.PURCHASER})),
    _metadata(UpdatePurchaseDraftCapability, frozenset({RoleCode.PURCHASER})),
    _metadata(UpdateWarehouseDraftCapability, frozenset({RoleCode.WAREHOUSE_MANAGER})),
)
