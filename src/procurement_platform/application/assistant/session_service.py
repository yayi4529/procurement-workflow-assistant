from procurement_platform.domain.assistant_session import (
    AgentConversation,
    AgentMessagePage,
    AgentMessageWriteResult,
    AgentSessionState,
    AgentSessionStateUpdate,
)
from procurement_platform.domain.enums import AgentMessageSender
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import RequirementDetail
from procurement_platform.ports.backend_client import BackendClient


class AssistantSessionService:
    def __init__(self, backend_client: BackendClient) -> None:
        self._backend_client = backend_client

    async def active(self, *, identity: PlatformIdentity) -> AgentConversation:
        return await self._backend_client.get_or_create_agent_conversation(
            identity=identity, current_action="ASSISTANT_CHAT"
        )

    async def append(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
        sender: AgentMessageSender,
        content: str,
    ) -> AgentMessageWriteResult:
        return await self._backend_client.append_agent_message(
            identity=identity,
            conversation_id=conversation_id,
            external_message_id=external_message_id,
            sender_type=sender,
            content=content,
        )

    async def messages(
        self, *, identity: PlatformIdentity, conversation_id: int
    ) -> AgentMessagePage:
        probe = await self._backend_client.list_agent_messages(
            identity=identity, conversation_id=conversation_id, page=1, page_size=1
        )
        if probe.total <= 1:
            return probe
        page_size = 50
        last_page = (probe.total - 1) // page_size + 1
        return await self._backend_client.list_agent_messages(
            identity=identity,
            conversation_id=conversation_id,
            page=last_page,
            page_size=page_size,
        )

    async def state(self, *, identity: PlatformIdentity, conversation_id: int) -> AgentSessionState:
        return await self._backend_client.get_agent_state(
            identity=identity, conversation_id=conversation_id
        )

    async def requirement(
        self, *, identity: PlatformIdentity, requirement_id: int
    ) -> RequirementDetail:
        return await self._backend_client.get_requirement(
            identity=identity, requirement_id=requirement_id
        )

    async def save_state(
        self, *, identity: PlatformIdentity, conversation_id: int, state: AgentSessionStateUpdate
    ) -> None:
        await self._backend_client.update_agent_state(
            identity=identity, conversation_id=conversation_id, state=state
        )
