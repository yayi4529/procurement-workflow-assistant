from uuid import UUID

from procurement_platform.application.applicant.workflow_service import (
    ApplicantWorkflowService,
)
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import CardInteractionEvent
from procurement_platform.domain.interaction import InteractionView
from procurement_platform.domain.json_types import JsonValue
from procurement_platform.domain.requirement import ApplicantFieldsPatch


def _integer(value: JsonValue | None, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} is required")
    return int(value)


class ApplicantActionRouter:
    def __init__(self, workflow: ApplicantWorkflowService) -> None:
        self._workflow = workflow

    async def route(self, event: CardInteractionEvent) -> InteractionView:
        identity = PlatformIdentity.create(
            platform_type=PlatformType.FEISHU,
            platform_user_id=event.external_user_id,
        )
        value = event.action_value
        action = event.action_id
        if action == "applicant.home":
            return await self._workflow.home()
        if action == "applicant.start_new":
            return await self._workflow.start_new(identity)
        if action == "applicant.create_draft":
            raw = event.form_values.get("building_id", value.get("building_id"))
            return await self._workflow.create_draft(identity, _integer(raw, "building_id"))
        if action in {"applicant.open", "applicant.refresh"}:
            return await self._workflow.open(
                identity, _integer(value.get("requirement_id"), "requirement_id")
            )
        if action == "applicant.save":
            names = ApplicantFieldsPatch.model_fields
            patch = ApplicantFieldsPatch.model_validate(
                {name: event.form_values[name] for name in names if name in event.form_values}
            )
            return await self._workflow.save(
                identity,
                _integer(value.get("requirement_id"), "requirement_id"),
                _integer(value.get("expected_version"), "expected_version"),
                patch,
            )
        if action in {"applicant.prepare_submit", "applicant.prepare_resubmit"}:
            return await self._workflow.prepare(
                identity,
                _integer(value.get("requirement_id"), "requirement_id"),
                resubmit=action.endswith("resubmit"),
            )
        if action == "applicant.confirm_handler":
            employee = event.form_values.get("assigned_to_employee_id")
            return await self._workflow.confirm_handler(
                identity,
                _integer(value.get("requirement_id"), "requirement_id"),
                _integer(employee, "assigned_to_employee_id"),
                resubmit=value.get("resubmit") is True,
            )
        if action in {"applicant.confirm_submit", "applicant.confirm_resubmit"}:
            token = value.get("action_token")
            if not isinstance(token, str):
                raise ValueError("action_token is required")
            return await self._workflow.confirm(
                identity,
                _integer(value.get("requirement_id"), "requirement_id"),
                _integer(value.get("expected_version"), "expected_version"),
                _integer(value.get("assigned_to_employee_id"), "assigned_to_employee_id"),
                UUID(token),
                resubmit=action.endswith("resubmit"),
            )
        if action == "applicant.list":
            return await self._workflow.listing(identity, _integer(value.get("page", 1), "page"))
        raise ValueError("unsupported applicant action")
