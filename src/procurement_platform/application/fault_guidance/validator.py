from procurement_platform.domain.enums import ValidationStatus
from procurement_platform.domain.fault_guidance import CandidateItem, FaultDraftValidationResult

_ALLOWED_QUANTITY_EVIDENCE = {
    "USER_CONFIRMED",
    "USER_EXPLICIT_REQUEST",
    "BACKEND_FACT",
}


class FaultDraftValidator:
    def validate(self, item: CandidateItem) -> FaultDraftValidationResult:
        missing_fields: list[str] = []
        errors: list[str] = []
        if item.item_kind is None:
            errors.append("item_kind_required")
        if not item.item_name.strip():
            errors.append("item_name_required")
        if item.quantity is None:
            missing_fields.append("quantity")
        elif item.quantity <= 0:
            errors.append("quantity_must_be_positive")
        elif item.quantity_evidence not in _ALLOWED_QUANTITY_EVIDENCE:
            # An ungrounded model-suggested quantity must never be accepted, but it is
            # recoverable through one user clarification rather than a generic hard error.
            missing_fields.append("quantity")
        if item.unit is None or not item.unit.strip():
            missing_fields.append("unit")

        status = (
            ValidationStatus.INVALID
            if errors
            else (
                ValidationStatus.NEEDS_CLARIFICATION if missing_fields else ValidationStatus.VALID
            )
        )
        return FaultDraftValidationResult(
            status=status,
            missing_fields=missing_fields,
            errors=errors,
        )
