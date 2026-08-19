from pydantic import Field

from procurement_platform.application.assistant.tooling.common import (
    SessionReferenceStore,
    StrictArgs,
)
from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult
from procurement_platform.domain.assistant_session import JsonValue, RecommendationReference
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.errors import BackendApplicationError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import ItemProductRecommendations, SelectedProduct
from procurement_platform.ports.backend_client import BackendClient


class RecommendProductsArgs(StrictArgs):
    request_item_id: int = Field(gt=0)
    top_k: int = Field(default=10, ge=1, le=10)


class RecommendProductsResult(AssistantToolResult):
    response: ItemProductRecommendations | None = None


class RecommendProductsCapability:
    name = "recommend_products"
    side_effect = "READ"
    description = (
        "Use this for product candidates for one specific purchase item. This is the first "
        "recommendation stage. request_item_id is required. Preserve backend ranking; do not "
        "infer compatibility or select a product. Read-only."
    )
    args_model = RecommendProductsArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)

    async def execute(
        self, *, args: RecommendProductsArgs, context: AssistantToolContext
    ) -> RecommendProductsResult:
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        try:
            response = await self._backend.recommend_products(
                identity=identity, request_item_id=args.request_item_id, top_k=args.top_k
            )
            refs = tuple(
                RecommendationReference(
                    reference_id=f"item-product:{args.request_item_id}:{item.rank}",
                    kind="ITEM_PRODUCT_RECOMMENDATION",
                    label=f"{item.brand or ''} {item.model or item.item_name}".strip(),
                )
                for item in response.recommendations
            )
            data: dict[str, JsonValue] = {
                f"recommendation:item:{args.request_item_id}:products": response.model_dump_json(),
                "recommendation:active_request_item_id": args.request_item_id,
            }
            for item, ref in zip(response.recommendations, refs, strict=True):
                selected = SelectedProduct(
                    product_key=item.product_key,
                    equipment_model_id=item.equipment_model_id,
                    equipment_category_id=response.query_context.equipment_category_id,
                    item_name=item.item_name,
                    brand=item.brand,
                    model=item.model,
                )
                data[f"recommendation:product:{ref.reference_id}"] = selected.model_dump_json()
            await self._session.save(
                identity=identity,
                context=context,
                requirement_id=response.query_context.request_id,
                references=refs,
                collected_data=data,
                awaiting_confirmation=response.status == "OK" and bool(refs),
            )
            return RecommendProductsResult(status="SUCCESS", response=response)
        except BackendApplicationError as exc:
            if exc.error_code == "PERMISSION_DENIED":
                return RecommendProductsResult(
                    status="PERMISSION_DENIED", user_message="无权查看该采购项的推荐"
                )
            if exc.error_code == "REQUEST_ITEM_NOT_FOUND":
                return RecommendProductsResult(
                    status="NOT_FOUND", user_message="对应采购项不存在或当前无法访问"
                )
            return RecommendProductsResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )
