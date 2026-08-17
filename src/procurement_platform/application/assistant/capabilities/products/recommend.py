from procurement_platform.application.assistant.tooling.applicant import (
    RecommendProductOptionsTool,
)


class RecommendProductsCapability(RecommendProductOptionsTool):
    name = "recommend_products"
    description = (
        "Recommend product candidates using authoritative backend evidence. Use it when "
        "the user asks for product options; it does not select or save a product. Read-only."
    )
