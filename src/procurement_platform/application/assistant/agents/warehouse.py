# ruff: noqa: RUF001

from procurement_platform.application.assistant.agents.base import BasicRoleAgent
from procurement_platform.application.assistant.prompts.warehouse import WAREHOUSE_PROMPT
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tooling import (
    UpdateWarehouseReceiptDraftResult,
)
from procurement_platform.application.warehouse.card_factory import WarehouseCardFactory
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.ports.backend_client import BackendClient


class WarehouseAgent(BasicRoleAgent):
    role = RoleCode.WAREHOUSE_MANAGER
    role_prompt = WAREHOUSE_PROMPT
    tool_names = frozenset({"query_purchase_requests", "update_warehouse_receipt_draft"})

    def __init__(
        self, session_service: AssistantSessionService, backend_client: BackendClient
    ) -> None:
        super().__init__(session_service)
        self._backend_client = backend_client

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if not isinstance(result, UpdateWarehouseReceiptDraftResult) or result.status != "SUCCESS":
            return await super().handle_tool_result(
                result=result, context=context, external_message_id=external_message_id
            )
        if not result.fields_complete:
            return None
        assert result.requirement_id is not None
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        detail = await self._backend_client.get_requirement(
            identity=identity, requirement_id=result.requirement_id
        )
        notice = "入库草稿已完整，请在正式仓库卡片中确认后完成入库。"
        await self._append_reply(context, external_message_id, notice)
        return AssistantInteractionResponse(
            view=WarehouseCardFactory().detail(detail, notice=notice)
        )
