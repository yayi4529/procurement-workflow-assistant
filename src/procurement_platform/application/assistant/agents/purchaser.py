from procurement_platform.application.assistant.agents.base import BasicRoleAgent
from procurement_platform.application.assistant.capabilities.policy import CapabilityPolicy
from procurement_platform.application.assistant.prompts.purchaser import PURCHASER_PROMPT
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tooling import (
    FillSelectedSupplierProfileResult,
    PreparePurchasePrefillResult,
    UpdatePurchaseExecutionDraftResult,
)
from procurement_platform.application.assistant.tools import ToolExecutor
from procurement_platform.application.purchaser.card_factory import PurchaserCardFactory
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.ports.backend_client import BackendClient


class PurchaserAgent(BasicRoleAgent):
    """LLM-directed purchaser assistant with deterministic tool and card boundaries."""

    role = RoleCode.PURCHASER
    role_prompt = PURCHASER_PROMPT

    def __init__(
        self,
        session_service: AssistantSessionService,
        tool_executor: ToolExecutor,
        backend_client: BackendClient,
        capability_policy: CapabilityPolicy | None = None,
    ) -> None:
        super().__init__(session_service, capability_policy)
        del tool_executor
        self._backend_client = backend_client

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if isinstance(result, PreparePurchasePrefillResult) and result.status == "SUCCESS":
            return None
        if isinstance(result, FillSelectedSupplierProfileResult) and result.status in {
            "SUCCESS",
            "NEED_MORE_INFORMATION",
        }:
            return None
        if isinstance(result, UpdatePurchaseExecutionDraftResult) and result.status == "SUCCESS":
            if not result.fields_complete:
                return None
            assert result.requirement_id is not None
            identity = PlatformIdentity.create(
                PlatformType(context.platform_type), context.platform_user_id
            )
            detail = await self._backend_client.get_requirement(
                identity=identity, requirement_id=result.requirement_id
            )
            notice = "采购执行草稿已完整, 请在正式采购卡片中审核并执行后续操作。"
            await self._append_reply(context, external_message_id, notice)
            return AssistantInteractionResponse(
                view=PurchaserCardFactory().detail(detail, notice=notice)
            )
        return await super().handle_tool_result(
            result=result, context=context, external_message_id=external_message_id
        )
