"""Compatibility imports for the original Task 03 V2 module.

The older Tool classes remain available for migration and tests.  These facades
are the only names registered for the optional Agent: their schemas describe a
single business action and deliberately hide the legacy ``operation`` router.
"""

from procurement_platform.application.assistant.capabilities.drafts import (
    UpdateApplicantDraftCapability,
    UpdatePurchaseDraftCapability,
    UpdateWarehouseDraftCapability,
)
from procurement_platform.application.assistant.capabilities.products import (
    RecommendProductsCapability,
)
from procurement_platform.application.assistant.capabilities.requirements import (
    GetPurchaseRequestCapability,
    GetPurchaseTimelineCapability,
    PurchaseRequestIdentifierArgs,
    SearchPurchaseRequestsArgs,
    SearchPurchaseRequestsCapability,
)
from procurement_platform.application.assistant.capabilities.suppliers import (
    ApplySupplierProfileCapability,
    GetSupplierProfileCapability,
    RecommendSuppliersCapability,
)

__all__ = (
    "ApplySupplierProfileCapability",
    "GetPurchaseRequestCapability",
    "GetPurchaseTimelineCapability",
    "GetSupplierProfileCapability",
    "PurchaseRequestIdentifierArgs",
    "RecommendProductsCapability",
    "RecommendSuppliersCapability",
    "SearchPurchaseRequestsArgs",
    "SearchPurchaseRequestsCapability",
    "UpdateApplicantDraftCapability",
    "UpdatePurchaseDraftCapability",
    "UpdateWarehouseDraftCapability",
)
