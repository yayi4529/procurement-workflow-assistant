from procurement_platform.adapters.backend.fake_client import FakeBackendClient
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
from procurement_platform.application.assistant.tools import ToolRegistry
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser, UserRole


def test_split_tooling_preserves_names_schemas_and_side_effects() -> None:
    backend = FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="Tool Test",
            mobile=None,
            status="ACTIVE",
            roles=tuple(UserRole(role_code=role) for role in RoleCode),
            buildings=(),
        )
    )
    registry = ToolRegistry()
    for tool in (
        QueryPurchaseRequestsTool(backend),
        RecommendProductOptionsTool(backend),
        UpdatePurchaseDraftTool(backend),
        RecommendSuppliersForRequirementTool(backend),
        UpdateReviewDraftTool(backend),
        QuerySupplierProfileTool(backend),
        PreparePurchasePrefillTool(backend),
        FillSelectedSupplierProfileTool(backend),
        UpdatePurchaseExecutionDraftTool(backend),
        UpdateWarehouseReceiptDraftTool(backend),
    ):
        registry.register(tool)

    definitions = {
        item.name: item for item in registry.definitions(allowed_names=registry.registered_names)
    }
    assert set(definitions) == {
        "query_purchase_requests",
        "recommend_product_options",
        "update_purchase_draft",
        "recommend_suppliers_for_requirement",
        "update_review_draft",
        "query_supplier_profile",
        "prepare_purchase_prefill",
        "fill_selected_supplier_profile",
        "update_purchase_execution_draft",
        "update_warehouse_receipt_draft",
    }
    assert definitions["query_purchase_requests"].side_effect == "READ"
    assert definitions["prepare_purchase_prefill"].side_effect == "READ"
    for name in (
        "update_purchase_draft",
        "update_review_draft",
        "fill_selected_supplier_profile",
        "update_purchase_execution_draft",
        "update_warehouse_receipt_draft",
    ):
        assert definitions[name].side_effect == "MUTATE"
        assert definitions[name].parameters["additionalProperties"] is False
