from procurement_platform.application.assistant.prompts.common import COMMON_PROMPT
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolCall,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.enums import AgentMessageSender, PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity


class BasicRoleAgent:
    role: RoleCode
    role_prompt: str
    tool_names: frozenset[str]

    def __init__(self, session_service: AssistantSessionService) -> None:
        self._session_service = session_service

    def allowed_tool_names(self) -> frozenset[str]:
        return self.tool_names

    def allowed_tool_names_for(self, user_text: str) -> frozenset[str]:
        del user_text
        return self.allowed_tool_names()

    def retry_tool_name(self) -> str | None:
        return None

    def requires_tool_call(self, user_text: str) -> bool:
        del user_text
        return False

    def prepare_tool_call(self, call: AssistantToolCall, *, user_text: str) -> AssistantToolCall:
        del user_text
        return call

    def build_messages(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
    ) -> tuple[AssistantMessage, ...]:
        system = AssistantMessage(
            role="system",
            content=(
                f"{COMMON_PROMPT}{self.role_prompt}"
                f"当前激活角色:{self.role.value}; 时区:{context.timezone_name}。"
            ),
        )
        return (system, *history)

    async def before_run(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None:
        del context, history, user_text, external_message_id
        return None

    async def handle_content(
        self,
        *,
        content: str,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
        retry_count: int,
    ) -> AssistantResponse | None:
        del user_text, retry_count
        await self._append_reply(context, external_message_id, content)
        return AssistantTextResponse(text=content)

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if result.exact_render_required and result.user_message:
            await self._append_reply(context, external_message_id, result.user_message)
            return AssistantTextResponse(text=result.user_message)
        if result.status != "SUCCESS" and result.user_message:
            await self._append_reply(context, external_message_id, result.user_message)
            return AssistantTextResponse(text=result.user_message)
        return None

    async def _append_reply(
        self, context: AssistantToolContext, external_message_id: str, text: str
    ) -> None:
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        await self._session_service.append(
            identity=identity,
            conversation_id=context.conversation_id,
            external_message_id=f"assistant:{external_message_id}",
            sender=AgentMessageSender.AGENT,
            content=text,
        )
