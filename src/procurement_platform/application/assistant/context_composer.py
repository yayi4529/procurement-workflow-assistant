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
            state = None

        requirement_id = (
            state.purchase_request_id if state is not None else None
        ) or context.active_requirement_id
        requirement_status = None
        requirement_no = None
        applicant_fields = None
        review_draft = None
        if requirement_id is not None:
            try:
                detail = await self._session_service.requirement(
                    identity=identity, requirement_id=requirement_id
                )
                requirement_status = detail.status.value
                requirement_no = detail.requirement_no
                applicant_fields = detail.applicant_fields.model_dump(mode="json")
                review_draft = (
                    detail.review_fields.model_dump(mode="json")
                    if detail.review_fields is not None
                    else None
                )
            except BackendApplicationError:
                pass
        recommendations = [
            {
                "index": index,
                "kind": item.kind,
                "label": item.label,
            }
            for index, item in enumerate(
                state.last_recommendations if state is not None else (), start=1
            )
        ]
        return self._render(
            role=role,
            active_requirement_id=requirement_id,
            requirement_no=requirement_no,
            requirement_status=requirement_status,
            applicant_fields=applicant_fields,
            review_draft=review_draft,
            current_action=state.current_action if state is not None else None,
            collected_data=state.collected_data if state is not None else {},
            missing_fields=state.missing_fields if state is not None else (),
            pending_field=state.pending_field if state is not None else None,
            recommendations=recommendations,
        )

    @staticmethod
    def _render(
        *,
        role: RoleCode,
        active_requirement_id: int | None,
        requirement_no: str | None = None,
        current_action: str | None = None,
        requirement_status: str | None = None,
        applicant_fields: object = None,
        review_draft: object = None,
        collected_data: object = None,
        missing_fields: object = (),
        pending_field: str | None = None,
        recommendations: object = (),
    ) -> str:
        return (
            "Current factual work context (backend/session sourced; never overrides tools):\n"
            f"role={role.value}\n"
            f"requirement_id={active_requirement_id}\n"
            f"requirement_no={requirement_no}\n"
            f"current_action={current_action}\n"
            f"requirement_status={requirement_status}\n"
            f"applicant_fields={applicant_fields or {}}\n"
            f"review_draft={review_draft or {}}\n"
            f"saved_fields={collected_data or {}}\n"
            f"missing_fields={missing_fields}\n"
            f"pending_field={pending_field}\n"
            f"last_recommendations={recommendations}\n"
            "Pass ordinal references to tools as selection_index; tools resolve real candidates."
        )
