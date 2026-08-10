from typing import Protocol

from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantResponse,
    AssistantToolCall,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.enums import RoleCode


class RoleAgent(Protocol):
    role: RoleCode

    def allowed_tool_names(self) -> frozenset[str]: ...

    def allowed_tool_names_for(self, user_text: str) -> frozenset[str]: ...

    def retry_tool_name(self) -> str | None: ...

    def requires_tool_call(self, user_text: str) -> bool: ...

    def prepare_tool_call(
        self, call: AssistantToolCall, *, user_text: str
    ) -> AssistantToolCall: ...

    def build_messages(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
    ) -> tuple[AssistantMessage, ...]: ...

    async def before_run(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None: ...

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
