# ruff: noqa: RUF001

from procurement_platform.application.assistant.agent import ProcurementAgent
from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.task_context_service import (
    AgentTaskStateService,
    BusinessFactsBuilder,
)
from procurement_platform.application.assistant.turn_context import AgentTurnContext
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
)
from procurement_platform.domain.assistant_session import AgentSessionState, AgentSessionStateUpdate
from procurement_platform.domain.enums import AgentMessageSender, PlatformType, RoleCode
from procurement_platform.domain.errors import SessionNotFoundError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.user import CurrentUser
from procurement_platform.ports.backend_client import BackendClient

ROLE_LABELS: dict[RoleCode, str] = {
    RoleCode.APPLICANT: "需求人",
    RoleCode.BUILDING_MANAGER: "楼长",
    RoleCode.PURCHASER: "采购员",
    RoleCode.WAREHOUSE_MANAGER: "仓库管理员",
}


class AssistantService:
    def __init__(
        self,
        *,
        backend_client: BackendClient,
        session_service: AssistantSessionService,
        context_builder: AssistantContextBuilder,
        procurement_agent: ProcurementAgent,
        max_history_messages: int,
    ) -> None:
        self._backend_client = backend_client
        self._session_service = session_service
        self._context_builder = context_builder
        self._procurement_agent = procurement_agent
        self._max_history_messages = max_history_messages

    async def handle(self, event: TextMessageEvent) -> AssistantResponse:
        if event.external_message_id is None:
            return AssistantTextResponse(text="无法识别消息。")
        identity = PlatformIdentity.create(PlatformType.FEISHU, event.external_user_id)
        current_user = await self._backend_client.get_current_user(identity=identity)
        conversation = await self._session_service.active(identity=identity)
        write = await self._session_service.append(
            identity=identity,
            conversation_id=conversation.conversation_id,
            external_message_id=event.external_message_id,
            sender=AgentMessageSender.USER,
            content=event.text,
        )
        if write.duplicate:
            prior_reply = await self._prior_reply(
                identity=identity,
                conversation_id=conversation.conversation_id,
                external_message_id=event.external_message_id,
            )
            if prior_reply is not None:
                return AssistantTextResponse(text=prior_reply)
        try:
            state = await self._session_service.state(
                identity=identity, conversation_id=conversation.conversation_id
            )
        except SessionNotFoundError:
            state = None

        supported_roles = self._supported_roles(current_user)
        if not supported_roles:
            return await self._text_reply(
                identity,
                conversation.conversation_id,
                event.external_message_id,
                "当前身份没有可用的采购助手角色。",
            )
        if event.text.strip().startswith(("切换角色", "切换到")):
            selected = self._selected_role(event.text, supported_roles)
            if selected is None:
                return await self._text_reply(
                    identity,
                    conversation.conversation_id,
                    event.external_message_id,
                    "未识别要切换的角色。当前能力仍按您的全部采购角色开放。",
                )
            await self._save_focused_role(identity, conversation.conversation_id, state, selected)
            return await self._text_reply(
                identity,
                conversation.conversation_id,
                event.external_message_id,
                f"已将默认展示角色切换为{ROLE_LABELS[selected]}；可用能力仍包含您的全部采购角色。",
            )

        context = self._context_builder.build(
            identity=identity,
            conversation_id=conversation.conversation_id,
            external_message_id=event.external_message_id,
            external_conversation_id=event.chat_id,
            current_user=current_user,
            state=state,
        )
        history = await self._history(
            identity=identity,
            conversation_id=conversation.conversation_id,
            external_message_id=event.external_message_id,
        )
        active_requirement = None
        if state is not None and state.purchase_request_id is not None:
            active_requirement = await self._session_service.requirement(
                identity=identity, requirement_id=state.purchase_request_id
            )
        context_role = (
            state.focused_role
            if state is not None and state.focused_role in supported_roles
            else supported_roles[0]
        )
        turn_context = AgentTurnContext(
            current_user=current_user,
            active_role=context_role,
            session_state=state,
            active_requirement=active_requirement,
            recent_history=history,
            current_recommendations=state.last_recommendations if state is not None else (),
            tool_context=context,
            business_facts=BusinessFactsBuilder.build(current_user, active_requirement),
            task_state=AgentTaskStateService.from_session(state),
        )
        return await self._procurement_agent.run(
            external_message_id=event.external_message_id,
            user_text=event.text,
            turn_context=turn_context,
        )

    async def _history(
        self, *, identity: PlatformIdentity, conversation_id: int, external_message_id: str
    ) -> tuple[AssistantMessage, ...]:
        page = await self._session_service.messages(
            identity=identity, conversation_id=conversation_id
        )
        target_index = next(
            (
                index
                for index, item in enumerate(page.items)
                if item.external_message_id == external_message_id
            ),
            len(page.items) - 1,
        )
        return tuple(
            AssistantMessage(
                role="user" if item.sender_type is AgentMessageSender.USER else "assistant",
                content=item.content,
            )
            for item in page.items[: target_index + 1][-self._max_history_messages :]
        )

    async def _prior_reply(
        self, *, identity: PlatformIdentity, conversation_id: int, external_message_id: str
    ) -> str | None:
        page = await self._session_service.messages(
            identity=identity, conversation_id=conversation_id
        )
        return next(
            (
                item.content
                for item in reversed(page.items)
                if item.external_message_id == f"assistant:{external_message_id}"
            ),
            None,
        )

    async def _save_focused_role(
        self,
        identity: PlatformIdentity,
        conversation_id: int,
        state: AgentSessionState | None,
        role: RoleCode,
    ) -> None:
        update = (
            AgentSessionStateUpdate.model_validate(
                state.model_dump(
                    exclude={"conversation_id", "expires_in_seconds", "restored_from_snapshot"}
                )
            )
            if state is not None
            else AgentSessionStateUpdate()
        )
        await self._session_service.save_state(
            identity=identity,
            conversation_id=conversation_id,
            state=update.model_copy(update={"focused_role": role}),
        )

    async def _text_reply(
        self,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
        text: str,
    ) -> AssistantTextResponse:
        await self._session_service.append(
            identity=identity,
            conversation_id=conversation_id,
            external_message_id=f"assistant:{external_message_id}",
            sender=AgentMessageSender.AGENT,
            content=text,
        )
        return AssistantTextResponse(text=text)

    @staticmethod
    def _supported_roles(current_user: CurrentUser) -> tuple[RoleCode, ...]:
        user_roles = {item.role_code for item in current_user.roles}
        return tuple(role for role in ROLE_LABELS if role in user_roles)

    @staticmethod
    def _selected_role(text: str, roles: tuple[RoleCode, ...]) -> RoleCode | None:
        normalized = text.strip().rstrip("。.!！")
        for prefix in ("切换角色", "切换到"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :].strip(" ：:")
        for role in roles:
            if normalized in {ROLE_LABELS[role], role.value}:
                return role
        return None
