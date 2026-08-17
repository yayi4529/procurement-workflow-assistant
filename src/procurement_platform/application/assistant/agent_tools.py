"""Deprecated compatibility facade for assistant tools.

Do not add tool implementations here. Use ``application.assistant.tooling``.
"""

from procurement_platform.application.assistant.tooling import (
    DraftUpdateResultBase as DraftUpdateResultBase,
)
from procurement_platform.application.assistant.tooling import (
    FillSelectedSupplierProfileArgs as FillSelectedSupplierProfileArgs,
)
from procurement_platform.application.assistant.tooling import (
    FillSelectedSupplierProfileResult as FillSelectedSupplierProfileResult,
)
from procurement_platform.application.assistant.tooling import (
    FillSelectedSupplierProfileTool as FillSelectedSupplierProfileTool,
)
from procurement_platform.application.assistant.tooling import (
    PreparePurchasePrefillArgs as PreparePurchasePrefillArgs,
)
from procurement_platform.application.assistant.tooling import (
    PreparePurchasePrefillResult as PreparePurchasePrefillResult,
)
from procurement_platform.application.assistant.tooling import (
    PreparePurchasePrefillTool as PreparePurchasePrefillTool,
)
from procurement_platform.application.assistant.tooling import (
    ProductOptionCandidate as ProductOptionCandidate,
)
from procurement_platform.application.assistant.tooling import (
    PurchasePrefillField as PurchasePrefillField,
)
from procurement_platform.application.assistant.tooling import (
    PurchasePrefillNotificationService as PurchasePrefillNotificationService,
)
from procurement_platform.application.assistant.tooling import (
    PurchasePrefillService as PurchasePrefillService,
)
from procurement_platform.application.assistant.tooling import (
    PurchaseRequestCandidate as PurchaseRequestCandidate,
)
from procurement_platform.application.assistant.tooling import (
    QueryPurchaseRequestsArgs as QueryPurchaseRequestsArgs,
)
from procurement_platform.application.assistant.tooling import (
    QueryPurchaseRequestsResult as QueryPurchaseRequestsResult,
)
from procurement_platform.application.assistant.tooling import (
    QueryPurchaseRequestsTool as QueryPurchaseRequestsTool,
)
from procurement_platform.application.assistant.tooling import (
    QuerySupplierProfileArgs as QuerySupplierProfileArgs,
)
from procurement_platform.application.assistant.tooling import (
    QuerySupplierProfileResult as QuerySupplierProfileResult,
)
from procurement_platform.application.assistant.tooling import (
    QuerySupplierProfileTool as QuerySupplierProfileTool,
)
from procurement_platform.application.assistant.tooling import (
    RecommendProductOptionsArgs as RecommendProductOptionsArgs,
)
from procurement_platform.application.assistant.tooling import (
    RecommendProductOptionsResult as RecommendProductOptionsResult,
)
from procurement_platform.application.assistant.tooling import (
    RecommendProductOptionsTool as RecommendProductOptionsTool,
)
from procurement_platform.application.assistant.tooling import (
    SessionReferenceStore as SessionReferenceStore,
)
from procurement_platform.application.assistant.tooling import (
    StrictArgs as StrictArgs,
)
from procurement_platform.application.assistant.tooling import (
    SupplierProfileCandidate as SupplierProfileCandidate,
)
from procurement_platform.application.assistant.tooling import (
    UpdatePurchaseDraftArgs as UpdatePurchaseDraftArgs,
)
from procurement_platform.application.assistant.tooling import (
    UpdatePurchaseDraftResult as UpdatePurchaseDraftResult,
)
from procurement_platform.application.assistant.tooling import (
    UpdatePurchaseDraftTool as UpdatePurchaseDraftTool,
)
from procurement_platform.application.assistant.tooling import (
    UpdatePurchaseExecutionDraftArgs as UpdatePurchaseExecutionDraftArgs,
)
from procurement_platform.application.assistant.tooling import (
    UpdatePurchaseExecutionDraftResult as UpdatePurchaseExecutionDraftResult,
)
from procurement_platform.application.assistant.tooling import (
    UpdatePurchaseExecutionDraftTool as UpdatePurchaseExecutionDraftTool,
)
from procurement_platform.application.assistant.tooling import (
    UpdateReviewDraftArgs as UpdateReviewDraftArgs,
)
from procurement_platform.application.assistant.tooling import (
    UpdateReviewDraftResult as UpdateReviewDraftResult,
)
from procurement_platform.application.assistant.tooling import (
    UpdateReviewDraftTool as UpdateReviewDraftTool,
)
from procurement_platform.application.assistant.tooling import (
    UpdateWarehouseReceiptDraftArgs as UpdateWarehouseReceiptDraftArgs,
)
from procurement_platform.application.assistant.tooling import (
    UpdateWarehouseReceiptDraftResult as UpdateWarehouseReceiptDraftResult,
)
from procurement_platform.application.assistant.tooling import (
    UpdateWarehouseReceiptDraftTool as UpdateWarehouseReceiptDraftTool,
)

__all__ = (
    "DraftUpdateResultBase",
    "FillSelectedSupplierProfileArgs",
    "FillSelectedSupplierProfileResult",
    "FillSelectedSupplierProfileTool",
    "PreparePurchasePrefillArgs",
    "PreparePurchasePrefillResult",
    "PreparePurchasePrefillTool",
    "ProductOptionCandidate",
    "PurchasePrefillField",
    "PurchasePrefillNotificationService",
    "PurchasePrefillService",
    "PurchaseRequestCandidate",
    "QueryPurchaseRequestsArgs",
    "QueryPurchaseRequestsResult",
    "QueryPurchaseRequestsTool",
    "QuerySupplierProfileArgs",
    "QuerySupplierProfileResult",
    "QuerySupplierProfileTool",
    "RecommendProductOptionsArgs",
    "RecommendProductOptionsResult",
    "RecommendProductOptionsTool",
    "SessionReferenceStore",
    "StrictArgs",
    "SupplierProfileCandidate",
    "UpdatePurchaseDraftArgs",
    "UpdatePurchaseDraftResult",
    "UpdatePurchaseDraftTool",
    "UpdatePurchaseExecutionDraftArgs",
    "UpdatePurchaseExecutionDraftResult",
    "UpdatePurchaseExecutionDraftTool",
    "UpdateReviewDraftArgs",
    "UpdateReviewDraftResult",
    "UpdateReviewDraftTool",
    "UpdateWarehouseReceiptDraftArgs",
    "UpdateWarehouseReceiptDraftResult",
    "UpdateWarehouseReceiptDraftTool",
)
