class AssistantError(Exception):
    pass


class LlmConfigurationError(AssistantError):
    pass


class LlmUnavailableError(AssistantError):
    pass


class LlmTimeoutError(AssistantError):
    pass


class LlmRateLimitError(AssistantError):
    pass


class LlmAuthenticationError(AssistantError):
    pass


class LlmBadRequestError(AssistantError):
    pass


class LlmProviderError(AssistantError):
    pass


class LlmInvalidResponseError(AssistantError):
    pass


class UnknownAssistantToolError(AssistantError):
    pass


class AssistantToolArgumentsError(AssistantError):
    pass


class AssistantToolExecutionError(AssistantError):
    pass


class AssistantToolStepLimitError(AssistantError):
    pass
