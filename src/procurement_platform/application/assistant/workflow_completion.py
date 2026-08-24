from typing import Protocol

from procurement_platform.application.assistant.role_skills import RoleSkillRegistry
from procurement_platform.application.assistant.workflow_state import WorkflowStateService
from procurement_platform.application.assistant.workflow_transition import (
    WorkflowTransitionEvent,
    WorkflowTransitionService,
)
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.ports.backend_client import BackendClient


class WorkflowCompletionObserver(Protocol):
    async def completed(self, *, platform_user_id: str) -> None: ...


class BackendWorkflowCompletionObserver:
    def __init__(self, backend: BackendClient, skills: RoleSkillRegistry) -> None:
        self._backend = backend
        self._skills = skills
        self._states = WorkflowStateService(backend)
        self._transitions = WorkflowTransitionService()

    async def completed(self, *, platform_user_id: str) -> None:
        identity = PlatformIdentity.create(PlatformType.FEISHU, platform_user_id)
        conversation = await self._backend.get_or_create_agent_conversation(
            identity=identity, current_action="ASSISTANT_CHAT"
        )
        session = await self._backend.get_agent_state(
            identity=identity, conversation_id=conversation.conversation_id
        )
        state = self._states.from_session(session)
        skill = self._skills.get(RoleCode.APPLICANT)
        if state is None or skill is None or state.status.value != "AWAITING_CARD":
            return
        workflow = skill.workflows.get(state.workflow_name)
        if workflow is None:
            return
        transition = self._transitions.transition(
            state=state,
            workflow=workflow,
            event=WorkflowTransitionEvent.CARD_COMPLETED,
        )
        await self._states.save(
            identity=identity,
            conversation_id=conversation.conversation_id,
            session=session,
            workflow=transition.state,
        )
