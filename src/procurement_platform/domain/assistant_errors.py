class AssistantError(Exception):
    pass


class LlmConfigurationError(AssistantError):
    pass


class LlmUnavailableError(AssistantError):
    pass


class LlmTimeoutError(AssistantError):
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
