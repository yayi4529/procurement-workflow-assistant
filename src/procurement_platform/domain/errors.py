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
