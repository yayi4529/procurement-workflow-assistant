# ruff: noqa: RUF001

from procurement_platform.application.assistant.agent_router import (
    ROLE_LABELS,
    AgentRouter,
    RoleSelectionRequired,
)
from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.domain.assistant import (
    AssistantClarificationResponse,
    AssistantMessage,
    AssistantOption,
    AssistantResponse,
    AssistantTextResponse,
)
from procurement_platform.domain.assistant_session import (
    AgentSessionState,
    AgentSessionStateUpdate,
)
from procurement_platform.domain.enums import AgentMessageSender, PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.ports.backend_client import BackendClient


class AssistantService:
    def __init__(
        self,
        *,
        backend_client: BackendClient,
        session_service: AssistantSessionService,
        context_builder: AssistantContextBuilder,
        agent_router: AgentRouter,
        runtime: AssistantRuntime,
        max_history_messages: int,
    ) -> None:
        self._backend_client = backend_client
        self._session_service = session_service
        self._context_builder = context_builder
        self._agent_router = agent_router
        self._runtime = runtime
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
        except Exception:
            state = None

        user_roles = tuple(
            role for role in ROLE_LABELS if role in {item.role_code for item in current_user.roles}
        )
        explicit_switch = event.text.strip().startswith(("切换角色", "切换到"))
        selected = self._agent_router.selected_role(event.text, user_roles)
        if explicit_switch:
            if selected is None:
                return await self._role_selection_response(
                    identity,
                    conversation.conversation_id,
                    event.external_message_id,
                    user_roles,
                )
            await self._save_focused_role(identity, conversation.conversation_id, state, selected)
            return await self._text_reply(
                identity,
                conversation.conversation_id,
                event.external_message_id,
                f"已切换到{ROLE_LABELS[selected]}助手，请继续告诉我需要处理的内容。",
            )

        resolution = self._agent_router.resolve(current_user=current_user, state=state)
        if isinstance(resolution, RoleSelectionRequired):
            if selected is None:
                return await self._role_selection_response(
                    identity,
                    conversation.conversation_id,
                    event.external_message_id,
                    resolution.roles,
                )
            await self._save_focused_role(identity, conversation.conversation_id, state, selected)
            return await self._text_reply(
                identity,
                conversation.conversation_id,
                event.external_message_id,
                f"已选择{ROLE_LABELS[selected]}助手，请继续告诉我需要处理的内容。",
            )
        agent = resolution
        if state is None or state.focused_role != agent.role:
            await self._save_focused_role(identity, conversation.conversation_id, state, agent.role)
            state = await self._session_service.state(
                identity=identity, conversation_id=conversation.conversation_id
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
        return await self._runtime.run(
            agent=agent,
            context=context,
            history=history,
            user_text=event.text,
            external_message_id=event.external_message_id,
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

    async def _role_selection_response(
        self,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
        roles: tuple[RoleCode, ...],
    ) -> AssistantClarificationResponse:
        if not roles:
            response = AssistantClarificationResponse(
                question="当前身份没有可用的采购助手角色。", options=()
            )
        else:
            response = AssistantClarificationResponse(
                question="请选择当前工作角色，回复序号或角色名称：",
                options=tuple(
                    AssistantOption(label=ROLE_LABELS[role], value=role.value) for role in roles
                ),
            )
        rendered = "\n".join(
            (
                response.question,
                *(
                    f"{index}. {option.label}"
                    for index, option in enumerate(response.options, start=1)
                ),
            )
        )
        await self._session_service.append(
            identity=identity,
            conversation_id=conversation_id,
            external_message_id=f"assistant:{external_message_id}",
            sender=AgentMessageSender.AGENT,
            content=rendered,
        )
        return response

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
