"""LLM-visible requirement query capabilities."""

from pydantic import Field, model_validator

from procurement_platform.application.assistant.tooling.common import (
    PurchaseRequestQueryService,
    QueryPurchaseRequestsArgs,
    QueryPurchaseRequestsResult,
    StrictArgs,
    TimeField,
)
from procurement_platform.domain.assistant import AssistantToolContext
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
    time_field: TimeField = "CREATED_AT"
    device_name: str | None = Field(default=None, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=150)
    status: RequirementStatus | None = None
    result_limit: int = Field(default=10, ge=1, le=20)


class SearchPurchaseRequestsResult(QueryPurchaseRequestsResult):
    """Typed search observation."""


class GetPurchaseRequestResult(QueryPurchaseRequestsResult):
    """Typed authoritative-detail observation."""


class GetPurchaseTimelineResult(QueryPurchaseRequestsResult):
    """Typed timeline observation."""


class SearchPurchaseRequestsCapability:
    name = "search_purchase_requests"
    side_effect = "READ"
    description = (
        "Search purchase requests matching user-provided filters. Use it to find one or "
        "more requests; do not use it for a request's full detail or timeline. Read-only."
    )
    args_model = SearchPurchaseRequestsArgs

    def __init__(self, backend: BackendClient) -> None:
        self._service = PurchaseRequestQueryService(backend)

    async def execute(
        self, *, args: SearchPurchaseRequestsArgs, context: AssistantToolContext
    ) -> SearchPurchaseRequestsResult:
        legacy_args = QueryPurchaseRequestsArgs(
            operation="SEARCH", **args.model_dump(exclude_unset=True)
        )
        result = await self._service.search(args=legacy_args, context=context)
        return SearchPurchaseRequestsResult.model_validate(result.model_dump())


class GetPurchaseRequestCapability:
    name = "get_purchase_request"
    side_effect = "READ"
    description = (
        "Get one purchase request's authoritative detail by exactly one ID or request "
        "number. Do not use it to search or fetch a timeline. Read-only."
    )
    args_model = PurchaseRequestIdentifierArgs

    def __init__(self, backend: BackendClient) -> None:
        self._service = PurchaseRequestQueryService(backend)

    async def execute(
        self, *, args: PurchaseRequestIdentifierArgs, context: AssistantToolContext
    ) -> GetPurchaseRequestResult:
        legacy_args = QueryPurchaseRequestsArgs(operation="GET_DETAIL", **args.model_dump())
        result = await self._service.get_detail(args=legacy_args, context=context)
        return GetPurchaseRequestResult.model_validate(result.model_dump())


class GetPurchaseTimelineCapability:
    name = "get_purchase_timeline"
    side_effect = "READ"
    description = (
        "Get the authoritative workflow timeline for one purchase request by exactly one "
        "ID or request number. Do not use it for search or full detail. Read-only."
    )
    args_model = PurchaseRequestIdentifierArgs

    def __init__(self, backend: BackendClient) -> None:
        self._service = PurchaseRequestQueryService(backend)

    async def execute(
        self, *, args: PurchaseRequestIdentifierArgs, context: AssistantToolContext
    ) -> GetPurchaseTimelineResult:
        legacy_args = QueryPurchaseRequestsArgs(operation="GET_TIMELINE", **args.model_dump())
        result = await self._service.get_timeline(args=legacy_args, context=context)
        return GetPurchaseTimelineResult.model_validate(result.model_dump())
