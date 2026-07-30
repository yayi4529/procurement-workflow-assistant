class BackendApplicationError(Exception):
    def __init__(
        self,
        error_code: str,
        user_message: str,
        trace_id: str | None = None,
    ) -> None:
        super().__init__(user_message)
        self.error_code = error_code
        self.user_message = user_message
        self.trace_id = trace_id


class AuthenticationError(BackendApplicationError):
    pass


class PermissionDeniedError(BackendApplicationError):
    pass


class UserNotFoundError(BackendApplicationError):
    pass


class UserDisabledError(BackendApplicationError):
    pass


class SessionNotFoundError(BackendApplicationError):
    pass


class SessionExpiredError(BackendApplicationError):
    pass


class ConcurrentModificationError(BackendApplicationError):
    pass


class InvalidStatusError(BackendApplicationError):
    pass


class RequirementNotFoundError(BackendApplicationError):
    pass


class RequirementNotOwnedError(BackendApplicationError):
    pass


class MissingRequiredFieldsError(BackendApplicationError):
    pass


class InvalidHandlerError(BackendApplicationError):
    pass


class NoHandlerCandidateError(BackendApplicationError):
    pass


class DuplicateOperationError(BackendApplicationError):
    pass


class ValidationError(BackendApplicationError):
    pass


class BackendUnavailableError(BackendApplicationError):
    pass


class BackendTimeoutError(BackendApplicationError):
    pass


class BackendProtocolError(BackendApplicationError):
    pass


class UnknownBackendError(BackendApplicationError):
    pass


class FeishuError(Exception):
    pass


class FeishuVerificationError(FeishuError):
    pass


class FeishuDecryptionError(FeishuError):
    pass


class FeishuProtocolError(FeishuError):
    pass


class FeishuDeliveryError(FeishuError):
    pass


class FeishuTimeoutError(FeishuError):
    pass


class UnsupportedInboundEventError(FeishuError):
    pass


class UnsupportedCardActionError(FeishuError):
    pass


class NotificationError(Exception):
    pass


class NotificationAuthenticationError(NotificationError):
    pass


class NotificationHeaderMismatchError(NotificationError):
    pass


class NotificationEventUnsupportedError(NotificationError):
    pass


class NotificationPayloadValidationError(NotificationError):
    pass


class NotificationIdempotencyConflictError(NotificationError):
    pass


class NotificationInProgressError(NotificationError):
    pass


class NotificationDeliveryError(NotificationError):
    pass
