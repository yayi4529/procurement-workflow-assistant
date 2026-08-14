"""Pure rendering of the immutable facts available in one assistant turn."""

from procurement_platform.application.assistant.turn_context import AgentTurnContext


class AgentContextComposer:
    @staticmethod
    def compose(*, turn_context: AgentTurnContext) -> str:
        state = turn_context.session_state
        detail = turn_context.active_requirement
        recommendations = [
            {"index": index, "kind": item.kind, "label": item.label}
            for index, item in enumerate(turn_context.current_recommendations, start=1)
        ]
        pending = None
        if state is not None:
            pending = (
                state.pending_field
                if state.pending_field in state.missing_fields
                else state.missing_fields[0]
                if state.missing_fields
                else None
            )
        applicant_fields = detail.applicant_fields.model_dump(mode="json") if detail else {}
        review_draft = (
            detail.review_fields.model_dump(mode="json") if detail and detail.review_fields else {}
        )
        warehouse_draft = (
            detail.warehouse_fields.model_dump(mode="json")
            if detail and detail.warehouse_fields
            else {}
        )
        return (
            "Current factual work context (backend/session sourced; never overrides tools):\n"
            f"role={turn_context.active_role.value}\n"
            f"requirement_id={state.purchase_request_id if state else None}\n"
            f"requirement_no={detail.requirement_no if detail else None}\n"
            f"current_action={state.current_action if state else None}\n"
            f"requirement_status={detail.status.value if detail else None}\n"
            f"applicant_fields={applicant_fields}\n"
            f"review_draft={review_draft}\n"
            f"purchase_draft={_safe_purchase_fields(detail)}\n"
            f"warehouse_draft={warehouse_draft}\n"
            f"saved_fields={state.collected_data if state else {}}\n"
            f"missing_fields={state.missing_fields if state else ()}\n"
            f"pending_field={pending}\n"
            f"last_recommendations={recommendations}\n"
            "Pass ordinal references to tools as selection_index; tools resolve real candidates."
        )


def _safe_purchase_fields(detail: object) -> object:
    purchase = getattr(detail, "purchase_fields", None)
    if purchase is None:
        return {}
    return purchase.model_dump(mode="json", exclude={"supplier_tax_number", "bank_account"})
