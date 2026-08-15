"""Task 03 business-oriented capability facades.

The older Tool classes remain available for migration and tests.  These facades
are the only names registered for the optional Agent: their schemas describe a
single business action and deliberately hide the legacy ``operation`` router.
"""

from pydantic import Field, model_validator

from procurement_platform.application.assistant.supplier_recommendation import (
    RecommendSuppliersForRequirementTool,
)
from procurement_platform.application.assistant.tooling import (
    FillSelectedSupplierProfileTool,
    QueryPurchaseRequestsArgs,
    QueryPurchaseRequestsTool,
    QuerySupplierProfileTool,
    RecommendProductOptionsTool,
    UpdatePurchaseDraftTool,
    UpdatePurchaseExecutionDraftTool,
    UpdateWarehouseReceiptDraftTool,
)
from procurement_platform.application.assistant.tooling.common import (
    StrictArgs,
)
from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult
from procurement_platform.domain.enums import RequirementStatus
from procurement_platform.ports.backend_client import BackendClient


class PurchaseRequestIdentifierArgs(StrictArgs):
    requirement_id: int | None = Field(default=None, gt=0)
    requirement_no: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def exactly_one_identifier(self) -> "PurchaseRequestIdentifierArgs":
        if (self.requirement_id is None) == (self.requirement_no is None):
            raise ValueError("requirement_id or requirement_no is required, but not both")
        return self


class SearchPurchaseRequestsArgs(StrictArgs):
    time_expression: str | None = Field(default=None, max_length=50)
    time_field: str = "CREATED_AT"
    device_name: str | None = Field(default=None, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=150)
    status: RequirementStatus | None = None
    result_limit: int = Field(default=10, ge=1, le=20)


class SearchPurchaseRequestsCapability:
    name = "search_purchase_requests"
    side_effect = "READ"
    description = (
        "Search purchase requests using user-provided filters. Read-only; it does not "
        "fetch a single request's detail or timeline."
    )
    args_model = SearchPurchaseRequestsArgs

    def __init__(self, backend: BackendClient) -> None:
        self._delegate = QueryPurchaseRequestsTool(backend)

    async def execute(
        self, *, args: SearchPurchaseRequestsArgs, context: AssistantToolContext
    ) -> AssistantToolResult:
        legacy = QueryPurchaseRequestsArgs(
            operation="SEARCH", **args.model_dump(exclude_unset=True)
        )
        return await self._delegate.execute(args=legacy, context=context)


class GetPurchaseRequestCapability:
    name = "get_purchase_request"
    side_effect = "READ"
    description = (
        "Get the authoritative detail of one purchase request. Read-only; identify it "
        "by exactly one ID or request number."
    )
    args_model = PurchaseRequestIdentifierArgs

    def __init__(self, backend: BackendClient) -> None:
        self._delegate = QueryPurchaseRequestsTool(backend)

    async def execute(
        self, *, args: PurchaseRequestIdentifierArgs, context: AssistantToolContext
    ) -> AssistantToolResult:
        legacy = QueryPurchaseRequestsArgs(operation="GET_DETAIL", **args.model_dump())
        return await self._delegate.execute(args=legacy, context=context)


class GetPurchaseTimelineCapability:
    name = "get_purchase_timeline"
    side_effect = "READ"
    description = (
        "Show the authoritative workflow timeline for one purchase request. Read-only "
        "and does not change workflow state."
    )
    args_model = PurchaseRequestIdentifierArgs

    def __init__(self, backend: BackendClient) -> None:
        self._delegate = QueryPurchaseRequestsTool(backend)

    async def execute(
        self, *, args: PurchaseRequestIdentifierArgs, context: AssistantToolContext
    ) -> AssistantToolResult:
        legacy = QueryPurchaseRequestsArgs(operation="GET_TIMELINE", **args.model_dump())
        return await self._delegate.execute(args=legacy, context=context)


class RecommendProductsCapability(RecommendProductOptionsTool):
    name = "recommend_products"
    description = (
        "Recommend product candidates from backend data for a device request. Read-only; "
        "it does not save or select a product."
    )


class UpdateApplicantDraftCapability(UpdatePurchaseDraftTool):
    name = "update_applicant_draft"
    description = (
        "Create or incrementally update the applicant's purchase request draft. It "
        "never submits or advances the workflow."
    )


class GetSupplierProfileCapability(QuerySupplierProfileTool):
    name = "get_supplier_profile"
    description = (
        "Read authoritative fields from a selected supplier profile. It does not "
        "modify a purchase draft."
    )


class RecommendSuppliersCapability(RecommendSuppliersForRequirementTool):
    name = "recommend_suppliers"
    description = (
        "Recommend supplier candidates for a purchase request using backend evidence. "
        "Read-only; it does not select or save a supplier."
    )


class ApplySupplierProfileCapability(FillSelectedSupplierProfileTool):
    name = "apply_supplier_profile_to_draft"
    description = (
        "Apply authoritative data from the explicitly selected supplier to the purchase "
        "draft. It does not start or submit procurement."
    )


class UpdatePurchaseDraftCapability(UpdatePurchaseExecutionDraftTool):
    name = "update_purchase_draft"
    description = (
        "Update the purchaser's execution draft with user-confirmed values. It does "
        "not start, submit, or complete procurement."
    )


class UpdateWarehouseDraftCapability(UpdateWarehouseReceiptDraftTool):
    name = "update_warehouse_draft"
    description = "Update warehouse receipt draft fields. It never confirms completion."
