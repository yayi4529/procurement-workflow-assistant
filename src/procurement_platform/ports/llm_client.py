from typing import Protocol

from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantToolDefinition,
    AssistantTurn,
)


class LlmClient(Protocol):
    async def complete(
        self,
        *,
        messages: tuple[AssistantMessage, ...],
        tools: tuple[AssistantToolDefinition, ...],
        tool_choice: str | None = None,
    ) -> AssistantTurn: ...
