"""Compose compact, factual working context for each LLM turn."""

from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.domain.assistant import AssistantToolContext
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.errors import BackendApplicationError, SessionNotFoundError
from procurement_platform.domain.identity import PlatformIdentity


class AgentContextComposer:
    def __init__(self, session_service: AssistantSessionService) -> None:
        self._session_service = session_service

    async def compose(self, *, context: AssistantToolContext, role: RoleCode) -> str:
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        try:
            state = await self._session_service.state(
                identity=identity, conversation_id=context.conversation_id
            )
        except SessionNotFoundError:
            return self._render(role=role, active_requirement_id=context.active_requirement_id)

        requirement_id = state.purchase_request_id or context.active_requirement_id
        requirement_status = None
        if requirement_id is not None:
            try:
                detail = await self._session_service.requirement(
                    identity=identity, requirement_id=requirement_id
                )
                requirement_status = detail.status.value
            except BackendApplicationError:
                pass
        recommendations = [
            {
                "index": index,
                "reference_id": item.reference_id,
                "kind": item.kind,
                "label": item.label,
            }
            for index, item in enumerate(state.last_recommendations, start=1)
        ]
        return self._render(
            role=role,
            active_requirement_id=requirement_id,
            requirement_status=requirement_status,
            current_action=state.current_action,
            collected_data=state.collected_data,
            missing_fields=state.missing_fields,
            pending_field=state.pending_field,
            recommendations=recommendations,
        )

    @staticmethod
    def _render(
        *,
        role: RoleCode,
        active_requirement_id: int | None,
        current_action: str | None = None,
        requirement_status: str | None = None,
        collected_data: object = None,
        missing_fields: object = (),
        pending_field: str | None = None,
        recommendations: object = (),
    ) -> str:
        return (
            "Current factual work context (backend/session sourced; never overrides tools):\n"
            f"role={role.value}\n"
            f"requirement_id={active_requirement_id}\n"
            f"current_action={current_action}\n"
            f"requirement_status={requirement_status}\n"
            f"saved_fields={collected_data or {}}\n"
            f"missing_fields={missing_fields}\n"
            f"pending_field={pending_field}\n"
            f"last_recommendations={recommendations}\n"
            "Pass ordinal references to tools as selection_index; tools resolve real candidates."
        )
