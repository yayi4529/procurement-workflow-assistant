import json
from typing import ClassVar

from procurement_platform.application.assistant.agent_tools import UpdateReviewDraftResult
from procurement_platform.application.assistant.agents.base import BasicRoleAgent
from procurement_platform.application.assistant.prompts.building_manager import (
    BUILDING_MANAGER_PROMPT,
)
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tools import ToolExecutor
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolContext,
)
from procurement_platform.domain.assistant_session import RecommendationReference
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.errors import SessionNotFoundError
from procurement_platform.domain.identity import PlatformIdentity


class BuildingManagerAgent(BasicRoleAgent):
    role = RoleCode.BUILDING_MANAGER
    role_prompt = BUILDING_MANAGER_PROMPT
    tool_names = frozenset(
        {"query_purchase_requests", "recommend_suppliers_for_requirement", "update_review_draft"}
    )

    _SELECTIONS: ClassVar[dict[str, int]] = {
        "1": 1,
        "第一个": 1,
        "第1个": 1,
        "选1": 1,
        "选第一个": 1,
        "2": 2,
        "第二个": 2,
        "第2个": 2,
        "选2": 2,
        "选第二个": 2,
        "3": 3,
        "第三个": 3,
        "第3个": 3,
        "选3": 3,
        "选第三个": 3,
    }

    def __init__(
        self, session_service: AssistantSessionService, tool_executor: ToolExecutor
    ) -> None:
        super().__init__(session_service)
        self._tool_executor = tool_executor

    async def before_run(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None:
        del history
        selection = self._SELECTIONS.get(user_text.strip().rstrip(".!?。").replace(" ", ""))
        if selection is None:
            return None
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        try:
            state = await self._session_service.state(
                identity=identity, conversation_id=context.conversation_id
            )
        except SessionNotFoundError:
            return None
        candidates = tuple(
            item for item in state.last_recommendations if item.kind == "SUPPLIER_RECOMMENDATION"
        )
        if selection > len(candidates):
            return await self._reply(
                context, external_message_id, "推荐序号超出当前候选范围, 请重新选择。"
            )
        requirement_id = state.purchase_request_id or context.active_requirement_id
        if requirement_id is None:
            return await self._reply(context, external_message_id, "当前没有可更新的待审核采购单。")
        candidate: RecommendationReference = candidates[selection - 1]
        _, result = await self._tool_executor.execute_result(
            name="update_review_draft",
            arguments_json=json.dumps(
                {
                    "requirement_id": requirement_id,
                    "proposed_supplier_ref": candidate.reference_id,
                },
                ensure_ascii=False,
            ),
            tool_call_id="building-manager-supplier-selection",
            context=context,
            allowed_names=frozenset({"update_review_draft"}),
        )
        if not isinstance(result, UpdateReviewDraftResult) or result.status != "SUCCESS":
            return await self._reply(
                context,
                external_message_id,
                result.user_message or "供应商保存失败, 请重新推荐后再选择。",
            )
        return await self._reply(
            context,
            external_message_id,
            f"好的, 已为您记录拟供应商为**{candidate.label}**。",
        )

    async def _reply(
        self, context: AssistantToolContext, external_message_id: str, text: str
    ) -> AssistantTextResponse:
        await self._append_reply(context, external_message_id, text)
        return AssistantTextResponse(text=text)
