# ruff: noqa: RUF001

from typing import Protocol

from procurement_platform.application.applicant.card_factory import ApplicantCardFactory
from procurement_platform.application.assistant.agent import ProcurementAgent
from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.entity_references import (
    parse_requirement_reference,
)
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.task_context_service import (
    AgentTaskStateService,
    BusinessFactsBuilder,
)
from procurement_platform.application.assistant.turn_context import AgentTurnContext
from procurement_platform.application.fault_guidance.intent_router import FaultIntentRouter
from procurement_platform.domain.assistant import (
    AssistantInteractionResponse,
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
)
from procurement_platform.domain.assistant_session import AgentSessionState, AgentSessionStateUpdate
from procurement_platform.domain.enums import (
    AgentMessageSender,
    PlatformType,
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.errors import BackendApplicationError, SessionNotFoundError
from procurement_platform.domain.fault_guidance import FaultGuidanceResponse
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


class FaultGuidanceHandler(Protocol):
    async def start(self, conversation_id: int | str) -> None: ...

    async def is_active(self, conversation_id: int | str) -> bool: ...

    async def handle_message(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        user_message: str,
    ) -> FaultGuidanceResponse: ...


class AssistantService:
    def __init__(
        self,
        *,
        backend_client: BackendClient,
        session_service: AssistantSessionService,
        context_builder: AssistantContextBuilder,
        procurement_agent: ProcurementAgent,
        max_history_messages: int,
        fault_guidance_service: FaultGuidanceHandler | None = None,
        fault_intent_router: FaultIntentRouter | None = None,
    ) -> None:
        self._backend_client = backend_client
        self._session_service = session_service
        self._context_builder = context_builder
        self._procurement_agent = procurement_agent
        self._max_history_messages = max_history_messages
        self._fault_guidance_service = fault_guidance_service
        self._fault_intent_router = fault_intent_router

    async def handle(self, event: TextMessageEvent) -> AssistantResponse:
        if event.external_message_id is None:
            return AssistantTextResponse(text="无法识别消息。")
        identity = PlatformIdentity.create(PlatformType.FEISHU, event.external_user_id)
        current_user = await self._backend_client.get_current_user(identity=identity)
        conversation = await self._session_service.active(identity=identity)
        if self._is_reset_request(event.text):
            await self._session_service.complete(
                identity=identity,
                conversation_id=conversation.conversation_id,
            )
            conversation = await self._session_service.active(identity=identity)
            await self._session_service.append(
                identity=identity,
                conversation_id=conversation.conversation_id,
                external_message_id=event.external_message_id,
                sender=AgentMessageSender.USER,
                content=event.text,
            )
            return await self._text_reply(
                identity,
                conversation.conversation_id,
                event.external_message_id,
                "已清空上一段采购上下文，可以重新描述需求。",
            )
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
            return AssistantTextResponse(text="该消息正在处理中，请稍候。")
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
        fault_message = self._fault_message(event.text)
        fault_active = (
            self._fault_guidance_service is not None
            and await self._fault_guidance_service.is_active(conversation.conversation_id)
        )
        if (
            fault_message is None
            and not fault_active
            and self._fault_intent_router is not None
            and await self._fault_intent_router.is_fault_intent(event.text)
        ):
            fault_message = event.text.strip()
        if self._fault_guidance_service is not None and (fault_message is not None or fault_active):
            if RoleCode.APPLICANT not in supported_roles:
                return await self._text_reply(
                    identity,
                    conversation.conversation_id,
                    event.external_message_id,
                    "故障采购引导仅对需求人角色开放。",
                )
            if fault_message == "":
                await self._fault_guidance_service.start(conversation.conversation_id)
                return await self._text_reply(
                    identity,
                    conversation.conversation_id,
                    event.external_message_id,
                    "故障采购引导已开始，请描述资产和故障现象。例如：2号UPS最近老报警。",
                )
            try:
                fault_response = await self._fault_guidance_service.handle_message(
                    identity=identity,
                    conversation_id=conversation.conversation_id,
                    user_message=fault_message if fault_message is not None else event.text,
                )
            except BackendApplicationError:
                return await self._text_reply(
                    identity,
                    conversation.conversation_id,
                    event.external_message_id,
                    "采购草稿创建失败，已保留故障上下文，请稍后发送“确认”重试。",
                )
            await self._session_service.append(
                identity=identity,
                conversation_id=conversation.conversation_id,
                external_message_id=f"assistant:{event.external_message_id}",
                sender=AgentMessageSender.AGENT,
                content=fault_response.reply,
            )
            if fault_response.procurement_draft_ref is not None:
                requirement_id = parse_requirement_reference(fault_response.procurement_draft_ref)
                await self._save_purchase_request(
                    identity, conversation.conversation_id, state, requirement_id
                )
                detail = await self._backend_client.get_requirement(
                    identity=identity, requirement_id=requirement_id
                )
                return AssistantInteractionResponse(
                    view=ApplicantCardFactory().detail(
                        detail,
                        notice=fault_response.reply,
                        confirmation_mode=True,
                    )
                )
            return AssistantTextResponse(text=fault_response.reply)
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

        effective_state = state
        context = self._context_builder.build(
            identity=identity,
            conversation_id=conversation.conversation_id,
            external_message_id=event.external_message_id,
            external_conversation_id=event.chat_id,
            current_user=current_user,
            state=effective_state,
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
        if (
            state is not None
            and (
                state.focused_role if state.focused_role in supported_roles else supported_roles[0]
            )
            is RoleCode.APPLICANT
            and self._is_new_purchase_intent(event.text)
            and active_requirement is not None
            and active_requirement.status
            not in {RequirementStatus.DRAFT, RequirementStatus.REJECTED}
        ):
            effective_state = state.model_copy(update={"purchase_request_id": None})
            active_requirement = None
            context = self._context_builder.build(
                identity=identity,
                conversation_id=conversation.conversation_id,
                external_message_id=event.external_message_id,
                external_conversation_id=event.chat_id,
                current_user=current_user,
                state=effective_state,
            )
        context_role = (
            effective_state.focused_role
            if effective_state is not None and effective_state.focused_role in supported_roles
            else supported_roles[0]
        )
        turn_context = AgentTurnContext(
            current_user=current_user,
            active_role=context_role,
            session_state=effective_state,
            active_requirement=active_requirement,
            recent_history=history,
            current_recommendations=state.last_recommendations if state is not None else (),
            tool_context=context,
            business_facts=BusinessFactsBuilder.build(current_user, active_requirement),
            task_state=AgentTaskStateService.from_session(effective_state),
        )
        if (
            context_role is RoleCode.APPLICANT
            and state is not None
            and state.purchase_request_id is not None
            and self._is_confirmation_card_request(event.text)
        ):
            detail = await self._backend_client.get_requirement(
                identity=identity, requirement_id=state.purchase_request_id
            )
            notice = "请核对当前多采购项草稿，并通过下方确认卡提交。"
            await self._session_service.append(
                identity=identity,
                conversation_id=conversation.conversation_id,
                external_message_id=f"assistant:{event.external_message_id}",
                sender=AgentMessageSender.AGENT,
                content=notice,
            )
            return AssistantInteractionResponse(
                view=ApplicantCardFactory().detail(detail, notice=notice, confirmation_mode=True)
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
        message = await self._session_service.message_by_external_id(
            identity=identity,
            conversation_id=conversation_id,
            external_message_id=f"assistant:{external_message_id}",
        )
        return message.content if message is not None else None

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

    async def _save_purchase_request(
        self,
        identity: PlatformIdentity,
        conversation_id: int,
        state: AgentSessionState | None,
        requirement_id: int,
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
            state=update.model_copy(update={"purchase_request_id": requirement_id}),
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

    @staticmethod
    def _is_confirmation_card_request(text: str) -> bool:
        normalized = text.strip().lower()
        return "确认" in normalized and (
            "卡" in normalized or "提交" in normalized or "草稿" in normalized
        )

    @staticmethod
    def _is_reset_request(text: str) -> bool:
        return text.strip().rstrip("。.!！") in {
            "重新开始",
            "清空上下文",
            "新会话",
            "开始新需求",
        }

    @staticmethod
    def _is_new_purchase_intent(text: str) -> bool:
        normalized = "".join(text.strip().split())
        return normalized.startswith(
            ("我要买", "我要采购", "我要购买", "帮我买", "帮我采购")
        ) or normalized.startswith(("买", "采购", "购买"))

    @staticmethod
    def _fault_message(text: str) -> str | None:
        normalized = text.strip()
        if normalized == "故障引导":
            return ""
        for prefix in ("故障引导：", "故障引导:"):
            if normalized.startswith(prefix):
                return normalized[len(prefix) :].strip()
        return None
