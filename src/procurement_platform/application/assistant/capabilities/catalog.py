from typing import Protocol

from procurement_platform.application.assistant.capabilities.metadata import CapabilityMetadata
from procurement_platform.application.assistant.supplier_recommendation import (
    RecommendSuppliersForRequirementTool,
)
from procurement_platform.application.assistant.tooling import (
    FillSelectedSupplierProfileTool,
    PreparePurchasePrefillTool,
    QueryPurchaseRequestsTool,
    QuerySupplierProfileTool,
    RecommendProductOptionsTool,
    UpdatePurchaseDraftTool,
    UpdatePurchaseExecutionDraftTool,
    UpdateReviewDraftTool,
    UpdateWarehouseReceiptDraftTool,
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
    _metadata(QueryPurchaseRequestsTool, ALL_WORKFLOW_ROLES),
    _metadata(RecommendProductOptionsTool, frozenset({RoleCode.APPLICANT})),
    _metadata(UpdatePurchaseDraftTool, frozenset({RoleCode.APPLICANT})),
    _metadata(
        RecommendSuppliersForRequirementTool,
        frozenset({RoleCode.BUILDING_MANAGER}),
    ),
    _metadata(UpdateReviewDraftTool, frozenset({RoleCode.BUILDING_MANAGER})),
    _metadata(
        QuerySupplierProfileTool,
        frozenset({RoleCode.BUILDING_MANAGER, RoleCode.PURCHASER}),
    ),
    _metadata(PreparePurchasePrefillTool, frozenset({RoleCode.PURCHASER})),
    _metadata(FillSelectedSupplierProfileTool, frozenset({RoleCode.PURCHASER})),
    _metadata(UpdatePurchaseExecutionDraftTool, frozenset({RoleCode.PURCHASER})),
    _metadata(UpdateWarehouseReceiptDraftTool, frozenset({RoleCode.WAREHOUSE_MANAGER})),
)
