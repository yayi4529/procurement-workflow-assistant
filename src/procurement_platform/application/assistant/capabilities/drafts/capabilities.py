from procurement_platform.application.assistant.tooling.applicant import UpdatePurchaseDraftTool
from procurement_platform.application.assistant.tooling.building_manager import (
    UpdateReviewDraftTool,
)
from procurement_platform.application.assistant.tooling.purchaser import (
    UpdatePurchaseExecutionDraftTool,
)
from procurement_platform.application.assistant.tooling.warehouse import (
    UpdateWarehouseReceiptDraftTool,
)


class UpdateApplicantDraftCapability(UpdatePurchaseDraftTool):
    name = "update_applicant_draft"
    description = (
        "Create or incrementally update the applicant's purchase request draft. Use only "
        "for user-provided or confirmed fields; it never submits or advances the workflow."
    )


class UpdateReviewDraftCapability(UpdateReviewDraftTool):
    description = (
        "Update building-manager review draft fields. Use only for confirmed editable "
        "review data; it never approves, rejects, or advances the workflow."
    )


class UpdatePurchaseDraftCapability(UpdatePurchaseExecutionDraftTool):
    name = "update_purchase_draft"
    description = (
        "Update the purchaser's execution draft with user-confirmed values. It never "
        "starts, submits, or completes procurement."
    )


class UpdateWarehouseDraftCapability(UpdateWarehouseReceiptDraftTool):
    name = "update_warehouse_draft"
    description = (
        "Update warehouse receipt draft fields with user-confirmed values. It never "
        "confirms receipt or completes procurement."
    )
