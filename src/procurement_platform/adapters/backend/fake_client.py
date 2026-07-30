from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from procurement_platform.domain.assistant_session import (
    AgentConversation,
    AgentConversationCompletion,
    AgentMessage,
    AgentMessagePage,
    AgentMessageWriteResult,
    AgentSessionSnapshot,
    AgentSessionState,
    AgentSessionStateUpdate,
    AgentStateSaveResult,
)
from procurement_platform.domain.enums import AgentConversationStatus, AgentMessageSender
from procurement_platform.domain.errors import BackendApplicationError, SessionNotFoundError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.user import CurrentUser


@dataclass(frozen=True, slots=True)
class FakeCall:
    method: str
    conversation_id: int | None = None


class FakeBackendClient:
    def __init__(self, current_user: CurrentUser) -> None:
        self.current_user = current_user
        self.calls: list[FakeCall] = []
        self.call_counts: Counter[str] = Counter()
        self._failures: dict[str, BackendApplicationError] = {}
        self._conversations: dict[int, AgentConversation] = {}
        self._messages: dict[int, list[AgentMessage]] = {}
        self._external_ids: dict[tuple[int, str], AgentMessageWriteResult] = {}
        self._states: dict[int, AgentSessionState] = {}
        self.snapshots: list[AgentSessionSnapshot] = []
        self._next_conversation_id = 1
        self._next_message_id = 1

    def inject_error(self, method: str, error: BackendApplicationError) -> None:
        self._failures[method] = error

    def _record(self, method: str, conversation_id: int | None = None) -> None:
        self.calls.append(FakeCall(method, conversation_id))
        self.call_counts[method] += 1
        error = self._failures.get(method)
        if error is not None:
            raise error

    async def get_current_user(self, *, identity: PlatformIdentity) -> CurrentUser:
        self._record("get_current_user")
        return self.current_user

    async def get_or_create_agent_conversation(
        self, *, identity: PlatformIdentity, current_action: str
    ) -> AgentConversation:
        self._record("get_or_create_agent_conversation")
        for conversation in self._conversations.values():
            if (
                conversation.current_action == current_action
                and conversation.status is AgentConversationStatus.ACTIVE
            ):
                return conversation
        now = datetime.now(UTC)
        conversation_id = self._next_conversation_id
        self._next_conversation_id += 1
        conversation = AgentConversation(
            conversation_id=conversation_id,
            current_action=current_action,
            status=AgentConversationStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        self._conversations[conversation_id] = conversation
        self._messages[conversation_id] = []
        return conversation

    def _require_conversation(self, conversation_id: int) -> AgentConversation:
        try:
            return self._conversations[conversation_id]
        except KeyError as exc:
            raise SessionNotFoundError("SESSION_NOT_FOUND", "会话不存在") from exc

    async def append_agent_message(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
        sender_type: AgentMessageSender,
        content: str,
    ) -> AgentMessageWriteResult:
        self._record("append_agent_message", conversation_id)
        self._require_conversation(conversation_id)
        duplicate = self._external_ids.get((conversation_id, external_message_id))
        if duplicate is not None:
            return duplicate.model_copy(update={"duplicate": True})
        created_at = datetime.now(UTC)
        message_id = self._next_message_id
        self._next_message_id += 1
        message = AgentMessage(
            message_id=message_id,
            conversation_id=conversation_id,
            external_message_id=external_message_id,
            sender_type=sender_type,
            content=content,
            created_at=created_at,
        )
        self._messages[conversation_id].append(message)
        result = AgentMessageWriteResult(
            message_id=message_id,
            created_at=created_at,
            duplicate=False,
        )
        self._external_ids[(conversation_id, external_message_id)] = result
        return result

    async def list_agent_messages(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> AgentMessagePage:
        self._record("list_agent_messages", conversation_id)
        self._require_conversation(conversation_id)
        if page < 1 or not 1 <= page_size <= 200:
            raise ValueError("invalid pagination")
        messages = self._messages[conversation_id]
        start = (page - 1) * page_size
        return AgentMessagePage(
            items=tuple(messages[start : start + page_size]),
            page=page,
            page_size=page_size,
            total=len(messages),
        )

    async def get_agent_state(
        self, *, identity: PlatformIdentity, conversation_id: int
    ) -> AgentSessionState:
        self._record("get_agent_state", conversation_id)
        self._require_conversation(conversation_id)
        try:
            return self._states[conversation_id]
        except KeyError as exc:
            raise SessionNotFoundError("SESSION_NOT_FOUND", "会话状态不存在") from exc

    async def update_agent_state(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        state: AgentSessionStateUpdate,
    ) -> AgentStateSaveResult:
        self._record("update_agent_state", conversation_id)
        self._require_conversation(conversation_id)
        now = datetime.now(UTC)
        saved = AgentSessionState(
            conversation_id=conversation_id,
            expires_in_seconds=259200,
            **state.model_dump(),
        )
        self._states[conversation_id] = saved
        return AgentStateSaveResult(
            conversation_id=conversation_id,
            expires_in_seconds=saved.expires_in_seconds,
            updated_at=now,
        )

    async def snapshot_agent_state(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        snapshot_reason: str,
    ) -> AgentSessionSnapshot:
        self._record("snapshot_agent_state", conversation_id)
        self._require_conversation(conversation_id)
        snapshot = AgentSessionSnapshot(
            snapshot_id=len(self.snapshots) + 1,
            conversation_id=conversation_id,
            snapshot_reason=snapshot_reason,
            created_at=datetime.now(UTC),
        )
        self.snapshots.append(snapshot)
        return snapshot

    async def complete_agent_conversation(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        purchase_request_id: int | None,
    ) -> AgentConversationCompletion:
        self._record("complete_agent_conversation", conversation_id)
        conversation = self._require_conversation(conversation_id)
        now = datetime.now(UTC)
        self._conversations[conversation_id] = conversation.model_copy(
            update={"status": AgentConversationStatus.COMPLETED, "updated_at": now}
        )
        deleted = self._states.pop(conversation_id, None) is not None
        return AgentConversationCompletion(
            conversation_id=conversation_id,
            status=AgentConversationStatus.COMPLETED,
            redis_state_deleted=deleted,
            completed_at=now,
        )

    async def aclose(self) -> None:
        self._record("aclose")
