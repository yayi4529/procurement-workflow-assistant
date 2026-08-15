from procurement_platform.application.assistant.supplier_recommendation import (
    RecommendSuppliersForRequirementTool,
)
from procurement_platform.application.assistant.tooling.purchaser import (
    FillSelectedSupplierProfileTool,
    QuerySupplierProfileTool,
)


class GetSupplierProfileCapability(QuerySupplierProfileTool):
    name = "get_supplier_profile"
    description = (
        "Read authoritative fields for one selected supplier profile. Use only after a "
        "supplier is identified; it does not search suppliers or modify a draft. Read-only."
    )


class RecommendSuppliersCapability(RecommendSuppliersForRequirementTool):
    name = "recommend_suppliers"
    description = (
        "Recommend supplier candidates for a purchase request using backend evidence. "
        "It does not select a supplier or modify a draft. Read-only."
    )


class ApplySupplierProfileCapability(FillSelectedSupplierProfileTool):
    name = "apply_supplier_profile_to_draft"
    description = (
        "Apply authoritative backend data for an explicitly selected supplier to the "
        "purchase draft. It never starts or submits procurement."
    )
