from procurement_platform.application.assistant.agent_tools import PreparePurchasePrefillResult
from procurement_platform.application.assistant.agents.base import BasicRoleAgent
from procurement_platform.application.assistant.prompts.purchaser import PURCHASER_PROMPT
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantResponse,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.interaction import InteractionView, KeyValueField, KeyValueSection


class PurchaserAgent(BasicRoleAgent):
    role = RoleCode.PURCHASER
    role_prompt = PURCHASER_PROMPT
    tool_names = frozenset(
        {
            "query_purchase_requests",
            "query_supplier_profile",
            "prepare_purchase_prefill",
            "update_purchase_execution_draft",
        }
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
