import json
import re

from procurement_platform.application.assistant.agent_tools import (
    PreparePurchasePrefillResult,
    UpdatePurchaseExecutionDraftResult,
)
from procurement_platform.application.assistant.agents.base import BasicRoleAgent
from procurement_platform.application.assistant.prompts.purchaser import PURCHASER_PROMPT
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tools import ToolExecutor
from procurement_platform.application.purchaser.card_factory import PurchaserCardFactory
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.assistant_session import AgentSessionStateUpdate
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.errors import SessionNotFoundError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import InteractionView, KeyValueField, KeyValueSection
from procurement_platform.ports.backend_client import BackendClient


class PurchaserAgent(BasicRoleAgent):
    role = RoleCode.PURCHASER
    role_prompt = PURCHASER_PROMPT
    tool_names = frozenset(
        {
            "query_purchase_requests",
            "query_supplier_profile",
            "prepare_purchase_prefill",
            "fill_selected_supplier_profile",
            "update_purchase_execution_draft",
        }
    )

    def __init__(
        self,
        session_service: AssistantSessionService,
        tool_executor: ToolExecutor,
        backend_client: BackendClient,
    ) -> None:
        super().__init__(session_service)
        self._tool_executor = tool_executor
        self._backend_client = backend_client

    async def before_run(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None:
        del history
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        opened = await self._open_requirement_card(
            identity=identity,
            context=context,
            user_text=user_text,
            external_message_id=external_message_id,
        )
        if opened is not None:
            return opened
        try:
            state = await self._session_service.state(
                identity=identity, conversation_id=context.conversation_id
            )
        except SessionNotFoundError:
            return None
        requirement_id = state.purchase_request_id or context.active_requirement_id
        if requirement_id is None:
            return None
        contextual = await self._handle_contextual_supplier_request(
            context=context,
            user_text=user_text,
            external_message_id=external_message_id,
            requirement_id=requirement_id,
        )
        if contextual is not None:
            return contextual
        value: str | None = None
        if state.pending_field == "actual_unit_price":
            match = re.fullmatch(
                r"\s*(?:实际单价)?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(?:元)?\s*", user_text
            )
            if match is not None:
                value = match.group(1)
        if value is None:
            return None
        arguments = {"requirement_id": requirement_id, state.pending_field: value}
        _, result = await self._tool_executor.execute_result(
            name="update_purchase_execution_draft",
            arguments_json=json.dumps(arguments, ensure_ascii=False),
            tool_call_id="purchaser-pending-field",
            context=context,
            allowed_names=frozenset({"update_purchase_execution_draft"}),
        )
        if not isinstance(result, UpdatePurchaseExecutionDraftResult):
            return None
        if result.status == "SUCCESS":
            detail = await self._backend_client.get_requirement(
                identity=identity, requirement_id=requirement_id
            )
            text = "好的, 已保存采购执行信息。请在正式采购卡片中审核后提交仓库。"
            await self._append_reply(context, external_message_id, text)
            return AssistantInteractionResponse(
                view=PurchaserCardFactory().detail(detail, notice=text)
            )
        else:
            text = result.user_message or "采购执行信息保存失败, 请重新提供该字段。"
        await self._append_reply(context, external_message_id, text)
        return AssistantTextResponse(text=text)

    async def _open_requirement_card(
        self,
        *,
        identity: PlatformIdentity,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if "打开" not in user_text:
            return None
        match = re.search(r"\bPR-[A-Za-z0-9-]+\b", user_text, re.IGNORECASE)
        if match is None:
            return None
        requirement_no = match.group(0).upper()
        page = await self._backend_client.list_purchase_records(
            identity=identity,
            requirement_no=requirement_no,
            page=1,
            page_size=20,
        )
        exact = tuple(item for item in page.items if item.requirement_no == requirement_no)
        if len(exact) != 1:
            text = "未找到该采购单, 请核对完整采购单编号。"
            await self._append_reply(context, external_message_id, text)
            return AssistantTextResponse(text=text)
        detail = await self._backend_client.get_requirement(
            identity=identity, requirement_id=exact[0].requirement_id
        )
        try:
            state = await self._session_service.state(
                identity=identity, conversation_id=context.conversation_id
            )
            update = AgentSessionStateUpdate.model_validate(
                state.model_dump(
                    exclude={"conversation_id", "expires_in_seconds", "restored_from_snapshot"}
                )
            )
        except SessionNotFoundError:
            update = AgentSessionStateUpdate()
        await self._session_service.save_state(
            identity=identity,
            conversation_id=context.conversation_id,
            state=update.model_copy(
                update={
                    "purchase_request_id": detail.requirement_id,
                    "focused_role": RoleCode.PURCHASER,
                }
            ),
        )
        notice = "已打开采购单, 请在正式采购卡片中审核并执行后续操作。"
        await self._append_reply(context, external_message_id, notice)
        return AssistantInteractionResponse(
            view=PurchaserCardFactory().detail(detail, notice=notice)
        )

    async def _handle_contextual_supplier_request(
        self,
        *,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
        requirement_id: int,
    ) -> AssistantResponse | None:
        normalized = user_text.replace(" ", "")
        fill_requested = any(
            marker in normalized for marker in ("填入采购单", "填到采购单", "带入采购单")
        )
        supplier_info_requested = "供应商" in normalized and any(
            marker in normalized
            for marker in ("信息", "资料", "税号", "开户", "账号", "地址", "联系人")
        )
        if not fill_requested and not supplier_info_requested:
            return None
        if fill_requested:
            name = "fill_selected_supplier_profile"
            arguments: dict[str, object] = {"requirement_id": requirement_id}
        else:
            name = "query_supplier_profile"
            arguments = {
                "requirement_id": requirement_id,
                "requested_fields": [
                    "UNIFIED_SOCIAL_CREDIT_CODE",
                    "BANK_NAME",
                    "BANK_ACCOUNT",
                    "REGISTERED_ADDRESS",
                    "CONTRACT_CONTACT_INFO",
                    "BLACKLIST_STATUS",
                ],
            }
        _, result = await self._tool_executor.execute_result(
            name=name,
            arguments_json=json.dumps(arguments, ensure_ascii=False),
            tool_call_id="purchaser-contextual-supplier",
            context=context,
            allowed_names=frozenset({name}),
        )
        if fill_requested and result.status == "SUCCESS":
            identity = PlatformIdentity.create(
                PlatformType(context.platform_type), context.platform_user_id
            )
            detail = await self._backend_client.get_requirement(
                identity=identity, requirement_id=requirement_id
            )
            notice = result.user_message or "供应商主数据已保存到采购单。"
            await self._append_reply(context, external_message_id, notice)
            return AssistantInteractionResponse(
                view=PurchaserCardFactory().detail(detail, notice=notice)
            )
        return await self.handle_tool_result(
            result=result,
            context=context,
            external_message_id=external_message_id,
        )

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        if isinstance(result, PreparePurchasePrefillResult) and result.status == "SUCCESS":
            return AssistantInteractionResponse(view=self._prefill_view(result))
        return await super().handle_tool_result(
            result=result, context=context, external_message_id=external_message_id
        )

    @staticmethod
    def _prefill_view(result: PreparePurchasePrefillResult) -> InteractionView:
        return InteractionView(
            title="采购员预填推荐",
            subtitle="仅展示建议, 不会自动保存或提交",
            elements=(
                KeyValueSection(
                    fields=tuple(
                        KeyValueField(
                            label=item.field_name,
                            value=(
                                item.value
                                if item.value is not None
                                else "/".join(item.alternatives) or "待补充"
                            ),
                        )
                        for item in result.fields
                    )
                ),
            ),
        )
