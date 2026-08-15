from procurement_platform.application.assistant.capabilities.catalog import (
    DEFAULT_CAPABILITY_METADATA,
)
from procurement_platform.application.assistant.capabilities.policy import CapabilityPolicy
from procurement_platform.application.assistant.prompts.common import COMMON_PROMPT
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.enums import AgentMessageSender, PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity


class BasicRoleAgent:
    role: RoleCode
    role_prompt: str

    def __init__(
        self,
        session_service: AssistantSessionService,
        capability_policy: CapabilityPolicy | None = None,
    ) -> None:
        self._session_service = session_service
        self._capability_policy = capability_policy or CapabilityPolicy(DEFAULT_CAPABILITY_METADATA)
        self.tool_names = self._capability_policy.allowed_names_for_roles({self.role})

    def build_messages(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        working_context: str | None = None,
    ) -> tuple[AssistantMessage, ...]:
        system = AssistantMessage(
            role="system",
            content=(
                f"{COMMON_PROMPT}{self.role_prompt}"
                f"当前激活角色:{self.role.value}; 时区:{context.timezone_name}。"
            ),
        )
        context_message = (
            (AssistantMessage(role="system", content=working_context),) if working_context else ()
        )
        return (system, *context_message, *history)

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
