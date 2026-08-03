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

    async def complete(
        self, *, messages: tuple[AssistantMessage, ...], tools: tuple[AssistantToolDefinition, ...]
    ) -> AssistantTurn:
        del tools
        self.calls.append(messages)
        if not self._turns:
            raise LlmUnavailableError("fake LLM responses exhausted")
        return self._turns.popleft()
