from typing import Protocol
from uuid import UUID

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
from procurement_platform.domain.enums import (
    AgentMessageSender,
    RequirementStatus,
    RequirementView,
    RoleCode,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ApplicantFieldsPatch,
    ApplicantFieldsSaveResult,
    HandlerCandidates,
    RequirementDetail,
    RequirementPage,
    RequirementSummary,
    RequirementTransitionResult,
)
from procurement_platform.domain.user import CurrentUser


class BackendClient(Protocol):
    async def get_current_user(self, *, identity: PlatformIdentity) -> CurrentUser: ...

    async def create_requirement(
        self, *, identity: PlatformIdentity, building_id: int
    ) -> RequirementSummary: ...

    async def update_applicant_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: ApplicantFieldsPatch,
    ) -> ApplicantFieldsSaveResult: ...

    async def get_requirement(
        self, *, identity: PlatformIdentity, requirement_id: int
    ) -> RequirementDetail: ...

    async def list_requirements(
        self,
        *,
        identity: PlatformIdentity,
        view: RequirementView,
        status: RequirementStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> RequirementPage: ...

    async def list_handler_candidates(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        target_role: RoleCode,
    ) -> HandlerCandidates: ...

    async def submit_review(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult: ...

    async def resubmit_review(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult: ...

    async def get_or_create_agent_conversation(
        self, *, identity: PlatformIdentity, current_action: str
    ) -> AgentConversation: ...

    async def append_agent_message(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
        sender_type: AgentMessageSender,
        content: str,
    ) -> AgentMessageWriteResult: ...

    async def list_agent_messages(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> AgentMessagePage: ...

    async def get_agent_state(
        self, *, identity: PlatformIdentity, conversation_id: int
    ) -> AgentSessionState: ...

    async def update_agent_state(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        state: AgentSessionStateUpdate,
    ) -> AgentStateSaveResult: ...

    async def snapshot_agent_state(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        snapshot_reason: str,
    ) -> AgentSessionSnapshot: ...

    async def complete_agent_conversation(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        purchase_request_id: int | None,
    ) -> AgentConversationCompletion: ...

    async def aclose(self) -> None: ...
