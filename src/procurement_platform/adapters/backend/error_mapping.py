from procurement_platform.domain.errors import (
    AuthenticationError,
    BackendApplicationError,
    BackendUnavailableError,
    ConcurrentModificationError,
    PermissionDeniedError,
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
    "REQUIREMENT_NOT_OWNED",
    "INVALID_HANDLER",
    "NO_HANDLER_CANDIDATE",
}
_VALIDATION_CODES = {
    "REQUIREMENT_NOT_FOUND",
    "INVALID_STATUS",
    "INVALID_TRANSITION",
    "MISSING_REQUIRED_FIELDS",
    "SUPPLIER_NOT_FOUND",
    "SUPPLIER_MATCH_CONFLICT",
    "SUPPLIER_BLACKLISTED",
    "SUPPLIER_ALREADY_BLACKLISTED",
    "DUPLICATE_OPERATION",
    "INVALID_ACTION_TOKEN",
    "VALIDATION_ERROR",
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
    if code in _VALIDATION_CODES:
        return ValidationError(code, message, trace_id)
    if code == "INTERNAL_ERROR":
        return BackendUnavailableError(code, message, trace_id)
    return UnknownBackendError(code, message, trace_id)
