from procurement_platform.application.assistant.capabilities.policy import CapabilityPolicy
from procurement_platform.application.assistant.grounding import GroundingPolicy
from procurement_platform.application.assistant.presentation import LegacyToolResultPresenter
from procurement_platform.application.assistant.prompts.common import COMMON_PROMPT
from procurement_platform.application.assistant.prompts.procurement import PROCUREMENT_AGENT_PROMPT
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.turn_context import AgentTurnContext
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.enums import AgentMessageSender, PlatformType
from procurement_platform.domain.identity import PlatformIdentity


class ProcurementAgent:
    """Single procurement-domain agent; roles only affect capability authorization."""

    def __init__(
        self,
        *,
        runtime: AssistantRuntime,
        capability_policy: CapabilityPolicy,
        session_service: AssistantSessionService,
        result_presenter: LegacyToolResultPresenter,
        grounding_policy: GroundingPolicy | None = None,
    ) -> None:
        self._runtime = runtime
        self._capability_policy = capability_policy
        self._session_service = session_service
        self._result_presenter = result_presenter
        self._grounding_policy = grounding_policy or GroundingPolicy()

    async def run(
        self,
        *,
        turn_context: AgentTurnContext,
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse:
        allowed_names = self._capability_policy.allowed_names_for(turn_context.current_user)
        grounding = self._grounding_policy.decide(user_text, available_tools=allowed_names)
        return await self._runtime.run(
            agent=self,
            allowed_names=allowed_names,
            turn_context=turn_context,
            user_text=user_text,
            external_message_id=external_message_id,
            grounding=grounding,
        )

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
                f"{COMMON_PROMPT}{PROCUREMENT_AGENT_PROMPT}当前时区:{context.timezone_name}。"
            ),
        )
        context_messages = (
            (AssistantMessage(role="system", content=working_context),) if working_context else ()
        )
        return (system, *context_messages, *history)

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
        await self._session_service.append(
            identity=PlatformIdentity.create(
                PlatformType(context.platform_type), context.platform_user_id
            ),
            conversation_id=context.conversation_id,
            external_message_id=f"assistant:{external_message_id}",
            sender=AgentMessageSender.AGENT,
            content=content,
        )
        return AssistantTextResponse(text=content)

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        return await self._result_presenter.present(
            result=result,
            context=context,
            external_message_id=external_message_id,
        )
