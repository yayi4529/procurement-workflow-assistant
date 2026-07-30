from typing import TypeVar

from pydantic import BaseModel, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from procurement_platform.adapters.backend.dto import BackendEnvelope
from procurement_platform.adapters.backend.error_mapping import map_backend_error
from procurement_platform.adapters.backend.transport import SignedBackendTransport
from procurement_platform.domain.assistant_session import (
    AgentConversation,
    AgentConversationCompletion,
    AgentMessagePage,
    AgentMessageWriteResult,
    AgentSessionSnapshot,
    AgentSessionState,
    AgentSessionStateUpdate,
    AgentStateSaveResult,
)
from procurement_platform.domain.enums import AgentMessageSender
from procurement_platform.domain.errors import BackendProtocolError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.user import CurrentUser

ModelT = TypeVar("ModelT", bound=BaseModel)


class HttpBackendClient:
    def __init__(self, transport: SignedBackendTransport) -> None:
        self._transport = transport

    async def _request_model(
        self,
        model: type[ModelT],
        *,
        method: str,
        path: str,
        identity: PlatformIdentity,
        query: dict[str, str | int | None] | None = None,
        json_body: object | None = None,
    ) -> ModelT:
        raw = await self._transport.request(
            method=method,
            path=path,
            identity=identity,
            query=query,
            json_body=json_body,
        )
        try:
            envelope = TypeAdapter(BackendEnvelope[object]).validate_python(raw.payload)
        except PydanticValidationError as exc:
            raise BackendProtocolError(
                "BACKEND_INVALID_ENVELOPE",
                "采购后端响应结构不符合契约",
                raw.trace_id,
            ) from exc
        trace_id = envelope.trace_id or raw.trace_id
        if not 200 <= raw.status_code < 300 or not envelope.success:
            raise map_backend_error(envelope.code, envelope.message, trace_id)
        if envelope.data is None:
            raise BackendProtocolError(
                "BACKEND_MISSING_DATA",
                "采购后端成功响应缺少 data",
                trace_id,
            )
        try:
            return model.model_validate(envelope.data)
        except PydanticValidationError as exc:
            raise BackendProtocolError(
                "BACKEND_INVALID_DATA",
                "采购后端 data 不符合契约",
                trace_id,
            ) from exc

    async def get_current_user(self, *, identity: PlatformIdentity) -> CurrentUser:
        return await self._request_model(
            CurrentUser,
            method="GET",
            path="/api/v1/users/me",
            identity=identity,
        )

    async def get_or_create_agent_conversation(
        self, *, identity: PlatformIdentity, current_action: str
    ) -> AgentConversation:
        return await self._request_model(
            AgentConversation,
            method="POST",
            path="/api/v1/agent/conversations/active",
            identity=identity,
            json_body={"current_action": current_action},
        )

    async def append_agent_message(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
        sender_type: AgentMessageSender,
        content: str,
    ) -> AgentMessageWriteResult:
        return await self._request_model(
            AgentMessageWriteResult,
            method="POST",
            path=f"/api/v1/agent/conversations/{conversation_id}/messages",
            identity=identity,
            json_body={
                "external_message_id": external_message_id,
                "sender_type": sender_type.value,
                "content": content,
            },
        )

    async def list_agent_messages(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> AgentMessagePage:
        if page < 1:
            raise ValueError("page must be at least 1")
        if not 1 <= page_size <= 200:
            raise ValueError("page_size must be between 1 and 200")
        return await self._request_model(
            AgentMessagePage,
            method="GET",
            path=f"/api/v1/agent/conversations/{conversation_id}/messages",
            identity=identity,
            query={"page": page, "page_size": page_size},
        )

    async def get_agent_state(
        self, *, identity: PlatformIdentity, conversation_id: int
    ) -> AgentSessionState:
        return await self._request_model(
            AgentSessionState,
            method="GET",
            path=f"/api/v1/agent/conversations/{conversation_id}/state",
            identity=identity,
        )

    async def update_agent_state(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        state: AgentSessionStateUpdate,
    ) -> AgentStateSaveResult:
        return await self._request_model(
            AgentStateSaveResult,
            method="PUT",
            path=f"/api/v1/agent/conversations/{conversation_id}/state",
            identity=identity,
            json_body=state.model_dump(mode="json"),
        )

    async def snapshot_agent_state(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        snapshot_reason: str,
    ) -> AgentSessionSnapshot:
        return await self._request_model(
            AgentSessionSnapshot,
            method="POST",
            path=f"/api/v1/agent/conversations/{conversation_id}/snapshot",
            identity=identity,
            json_body={"snapshot_reason": snapshot_reason},
        )

    async def complete_agent_conversation(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        purchase_request_id: int | None,
    ) -> AgentConversationCompletion:
        return await self._request_model(
            AgentConversationCompletion,
            method="POST",
            path=f"/api/v1/agent/conversations/{conversation_id}/complete",
            identity=identity,
            json_body={"purchase_request_id": purchase_request_id},
        )

    async def aclose(self) -> None:
        await self._transport.aclose()
