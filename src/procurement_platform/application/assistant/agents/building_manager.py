# ruff: noqa: RUF001

from procurement_platform.application.assistant.agents.base import BasicRoleAgent
from procurement_platform.application.assistant.capabilities.policy import CapabilityPolicy
from procurement_platform.application.assistant.prompts.building_manager import (
    BUILDING_MANAGER_PROMPT,
)
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tooling import UpdateReviewDraftResult
from procurement_platform.application.assistant.tools import ToolExecutor
from procurement_platform.application.building_manager.card_factory import (
    BuildingManagerCardFactory,
)
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.ports.backend_client import BackendClient


class BuildingManagerAgent(BasicRoleAgent):
    """Role boundary for agentic review assistance; natural language belongs to the LLM."""

    role = RoleCode.BUILDING_MANAGER
    role_prompt = BUILDING_MANAGER_PROMPT

    def __init__(
        self,
        session_service: AssistantSessionService,
        tool_executor: ToolExecutor,
        backend_client: BackendClient,
        capability_policy: CapabilityPolicy | None = None,
    ) -> None:
        super().__init__(session_service, capability_policy)
        # Keep the shared constructor contract; AssistantRuntime exclusively executes tools.
        del tool_executor
        self._backend_client = backend_client

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if not isinstance(result, UpdateReviewDraftResult) or result.status != "SUCCESS":
            return await super().handle_tool_result(
                result=result, context=context, external_message_id=external_message_id
            )
        if not result.fields_complete:
            return None

        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        requirement_id = result.requirement_id or context.active_requirement_id
        if requirement_id is None:
            return None
        detail = await self._backend_client.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        notice = "审核信息已完整，请在正式审核卡片中确认后执行审批、驳回或提交采购员。"
        await self._append_reply(context, external_message_id, notice)
        return AssistantInteractionResponse(
            view=BuildingManagerCardFactory().detail(detail, notice=notice)
        )
