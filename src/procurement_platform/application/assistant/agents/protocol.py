from typing import Protocol

from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.enums import RoleCode


class RoleAgent(Protocol):
    role: RoleCode
    tool_names: frozenset[str]
    role_prompt: str

    def build_messages(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        working_context: str | None = None,
        active_role: RoleCode | None = None,
    ) -> tuple[AssistantMessage, ...]: ...

    async def handle_content(
        self,
        *,
        content: str,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
        retry_count: int,
    ) -> AssistantResponse | None: ...

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None: ...
