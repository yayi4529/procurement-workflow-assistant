from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser

ROLE_TOOLS: dict[RoleCode, frozenset[str]] = {
    RoleCode.APPLICANT: frozenset(
        {"query_purchase_requests", "recommend_product_options", "update_purchase_draft"}
    ),
    RoleCode.BUILDING_MANAGER: frozenset(
        {
            "query_purchase_requests",
            "query_supplier_profile",
            "recommend_suppliers_for_requirement",
            "update_review_draft",
        }
    ),
    RoleCode.PURCHASER: frozenset(
        {
            "query_purchase_requests",
            "query_supplier_profile",
            "prepare_purchase_prefill",
            "fill_selected_supplier_profile",
            "update_purchase_execution_draft",
        }
    ),
    RoleCode.WAREHOUSE_MANAGER: frozenset(
        {"query_purchase_requests", "update_warehouse_receipt_draft"}
    ),
}


class ToolPolicy:
    def __init__(self, *, allow_fake_tools: bool = False) -> None:
        self._allow_fake_tools = allow_fake_tools

    def allowed_tool_names(
        self, *, current_user: CurrentUser, active_role: RoleCode
    ) -> frozenset[str]:
        roles = {item.role_code for item in current_user.roles}
        names: set[str] = set()
        if current_user.status == "ACTIVE" and active_role in roles:
            names.update(ROLE_TOOLS.get(active_role, frozenset()))
        if self._allow_fake_tools:
            names.add("echo_tool")
        return frozenset(names)
