from collections import deque

from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantToolDefinition,
    AssistantTurn,
)
from procurement_platform.domain.assistant_errors import LlmUnavailableError


class FakeLlmClient:
    def __init__(self, *, turns: tuple[AssistantTurn, ...]) -> None:
        self._turns = deque(turns)
        self.calls: list[tuple[AssistantMessage, ...]] = []
        self.tool_choices: list[str | None] = []

    async def complete(
        self,
        *,
        messages: tuple[AssistantMessage, ...],
        tools: tuple[AssistantToolDefinition, ...],
        tool_choice: str | None = None,
    ) -> AssistantTurn:
        del tools
        self.calls.append(messages)
        self.tool_choices.append(tool_choice)
        if not self._turns:
            raise LlmUnavailableError("fake LLM responses exhausted")
        return self._turns.popleft()

    async def aclose(self) -> None:
        return None
