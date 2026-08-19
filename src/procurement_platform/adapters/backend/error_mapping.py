from procurement_platform.domain.errors import (
    AuthenticationError,
    BackendApplicationError,
    BackendUnavailableError,
    ConcurrentModificationError,
    DuplicateOperationError,
    InvalidHandlerError,
    InvalidStatusError,
    MissingRequiredFieldsError,
    NoHandlerCandidateError,
    PermissionDeniedError,
    RequirementNotFoundError,
    RequirementNotOwnedError,
    SessionExpiredError,
    SessionNotFoundError,
    UnknownBackendError,
    UserDisabledError,
    UserNotFoundError,
    ValidationError,
)

_PERMISSION_CODES = {
    "ROLE_NOT_FOUND",
    "PERMISSION_DENIED",
    "BUILDING_NOT_ALLOWED",
}
_VALIDATION_CODES = {
    "INVALID_TRANSITION",
    "SUPPLIER_NOT_FOUND",
    "SUPPLIER_MATCH_CONFLICT",
    "SUPPLIER_BLACKLISTED",
    "SUPPLIER_ALREADY_BLACKLISTED",
    "INVALID_ACTION_TOKEN",
    "VALIDATION_ERROR",
    "ITEM_ALREADY_PURCHASED",
    "OVER_RECEIPT",
    "WAREHOUSE_NOT_REQUIRED",
}


def map_backend_error(
    code: str,
    message: str,
    trace_id: str | None,
) -> BackendApplicationError:
    if code in {"AUTHENTICATION_ERROR", "INVALID_SIGNATURE"}:
        return AuthenticationError(code, message, trace_id)
    if code == "USER_NOT_FOUND":
        return UserNotFoundError(code, message, trace_id)
    if code == "USER_DISABLED":
        return UserDisabledError(code, message, trace_id)
    if code in _PERMISSION_CODES:
        return PermissionDeniedError(code, message, trace_id)
    if code == "SESSION_NOT_FOUND":
        return SessionNotFoundError(code, message, trace_id)
    if code == "SESSION_EXPIRED":
        return SessionExpiredError(code, message, trace_id)
    if code == "CONCURRENT_MODIFICATION":
        return ConcurrentModificationError(code, message, trace_id)
    specific = {
        "REQUIREMENT_NOT_FOUND": RequirementNotFoundError,
        "REQUIREMENT_NOT_OWNED": RequirementNotOwnedError,
        "INVALID_STATUS": InvalidStatusError,
        "MISSING_REQUIRED_FIELDS": MissingRequiredFieldsError,
        "INVALID_HANDLER": InvalidHandlerError,
        "NO_HANDLER_CANDIDATE": NoHandlerCandidateError,
        "DUPLICATE_OPERATION": DuplicateOperationError,
    }
    if code in specific:
        return specific[code](code, message, trace_id)
    if code in _VALIDATION_CODES:
        return ValidationError(code, message, trace_id)
    if code == "INTERNAL_ERROR":
        return BackendUnavailableError(code, message, trace_id)
    return UnknownBackendError(code, message, trace_id)
