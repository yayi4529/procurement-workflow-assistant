from pydantic import Field, model_validator
from pydantic import ValidationError as PydanticValidationError

from procurement_platform.application.assistant.capabilities.products.recommend import (
    RecommendProductsArgs,
    RecommendProductsCapability,
)
from procurement_platform.application.assistant.supplier_recommendation import (
    RecommendSuppliersForRequirementArgs,
    RecommendSuppliersForRequirementTool,
)
from procurement_platform.application.assistant.tooling.common import (
    SessionReferenceStore,
    StrictArgs,
)
from procurement_platform.application.assistant.tooling.purchaser import (
    FillSelectedSupplierProfileTool,
    QuerySupplierProfileTool,
)
from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult
from procurement_platform.domain.assistant_session import JsonValue, RecommendationReference
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.errors import BackendApplicationError, SessionNotFoundError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ItemProductRecommendations,
    ItemSupplierRecommendations,
    SelectedProduct,
)
from procurement_platform.ports.backend_client import BackendClient


class GetSupplierProfileCapability(QuerySupplierProfileTool):
    name = "get_supplier_profile"
    description = "Read authoritative fields for one selected supplier profile. Read-only."


class RecommendSuppliersArgs(StrictArgs):
    request_item_id: int | None = Field(default=None, gt=0)
    requirement_id: int | None = Field(default=None, gt=0)
    product_ref: str | None = None
    top_k: int = Field(default=5, ge=1, le=5)

    @model_validator(mode="after")
    def require_scope(self) -> "RecommendSuppliersArgs":
        if self.request_item_id is None and self.requirement_id is None:
            raise ValueError("request_item_id is required")
        return self


class RecommendSuppliersResult(AssistantToolResult):
    response: ItemSupplierRecommendations | None = None
    product_response: ItemProductRecommendations | None = None


class RecommendSuppliersCapability:
    name = "recommend_suppliers"
    side_effect = "READ"
    description = (
        "Use only after a product returned for this request_item_id was selected, or when "
        "the item already specifies an exact product. Pass product_ref; omit it only for an "
        "already-specified item. Never select a supplier or modify procurement."
    )
    args_model = RecommendSuppliersArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)
        self._legacy = RecommendSuppliersForRequirementTool(backend)
        self._products = RecommendProductsCapability(backend)

    async def execute(
        self, *, args: RecommendSuppliersArgs, context: AssistantToolContext
    ) -> AssistantToolResult:
        if args.request_item_id is None:
            assert args.requirement_id is not None
            return await self._legacy.execute(
                args=RecommendSuppliersForRequirementArgs(
                    requirement_id=args.requirement_id, limit=min(args.top_k, 3)
                ),
                context=context,
            )
        request_item_id = args.request_item_id
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        try:
            try:
                state = await self._session.state(identity, context.conversation_id)
                data = state.collected_data
            except SessionNotFoundError:
                data = {}
            selected = self._selected_product(data, args, request_item_id)
            response = await self._backend.recommend_suppliers(
                identity=identity,
                request_item_id=request_item_id,
                selected_product=selected,
                top_k=args.top_k,
            )
            refs = tuple(
                RecommendationReference(
                    reference_id=f"item-supplier:{request_item_id}:{item.rank}",
                    kind="ITEM_SUPPLIER_RECOMMENDATION",
                    label=item.supplier_name,
                )
                for item in response.recommendations
            )
            saved_data: dict[str, JsonValue] = {
                f"recommendation:item:{request_item_id}:selected_product": (
                    response.selected_product.model_dump_json()
                ),
                f"recommendation:item:{request_item_id}:suppliers": response.model_dump_json(),
                "recommendation:active_request_item_id": request_item_id,
            }
            await self._session.save(
                identity=identity,
                context=context,
                requirement_id=response.query_context.request_id,
                references=refs,
                collected_data=saved_data,
                awaiting_confirmation=False,
            )
            return RecommendSuppliersResult(status="SUCCESS", response=response)
        except BackendApplicationError as exc:
            if exc.error_code == "SELECTED_PRODUCT_REQUIRED":
                product_result = await self._products.execute(
                    args=RecommendProductsArgs(request_item_id=request_item_id),
                    context=context,
                )
                return RecommendSuppliersResult(
                    status="NEED_MORE_INFORMATION",
                    user_message="需要先确定具体产品, 请从该采购项的历史产品候选中选择",
                    product_response=product_result.response,
                )
            messages = {
                "SELECTED_PRODUCT_MISMATCH": (
                    "INVALID_ARGUMENTS",
                    "该产品不是当前采购项的有效候选, 请重新选择",
                ),
                "REQUEST_ITEM_NOT_FOUND": ("NOT_FOUND", "对应采购项不存在或当前无法访问"),
                "PERMISSION_DENIED": ("PERMISSION_DENIED", "无权查看该采购项的推荐"),
            }
            if exc.error_code in messages:
                status, message = messages[exc.error_code]
                return RecommendSuppliersResult(status=status, user_message=message)
            return RecommendSuppliersResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )

    @staticmethod
    def _selected_product(
        data: dict[str, JsonValue], args: RecommendSuppliersArgs, request_item_id: int
    ) -> SelectedProduct | None:
        if args.product_ref is None:
            return None
        if not args.product_ref.startswith(f"item-product:{request_item_id}:"):
            raise BackendApplicationError("SELECTED_PRODUCT_MISMATCH", "产品候选不属于当前采购项")
        raw = data.get(f"recommendation:product:{args.product_ref}")
        if not isinstance(raw, str):
            raise BackendApplicationError("SELECTED_PRODUCT_MISMATCH", "产品候选不存在或已过期")
        try:
            selected = SelectedProduct.model_validate_json(raw)
        except PydanticValidationError as exc:
            raise BackendApplicationError(
                "SELECTED_PRODUCT_MISMATCH", "产品候选不存在或已过期"
            ) from exc
        return selected


class ApplySupplierProfileCapability(FillSelectedSupplierProfileTool):
    name = "apply_supplier_profile_to_draft"
    description = "Apply an explicitly selected supplier profile to a draft; never submit."
