from uuid import UUID

from procurement_platform.application.building_manager.workflow_service import (
    BuildingManagerWorkflowService,
)
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import CardInteractionEvent
from procurement_platform.domain.interaction import InteractionView
from procurement_platform.domain.json_types import JsonValue
from procurement_platform.domain.requirement import ReviewFieldsPatch


def _integer(value: JsonValue | None, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} is required")
    return int(value)


class BuildingManagerActionRouter:
    def __init__(self, workflow: BuildingManagerWorkflowService) -> None:
        self._workflow = workflow

    async def route(self, event: CardInteractionEvent) -> InteractionView:
        identity = PlatformIdentity.create(
            platform_type=PlatformType.FEISHU,
            platform_user_id=event.external_user_id,
        )
        value = event.action_value
        action = event.action_id
        requirement_id = (
            _integer(value.get("requirement_id"), "requirement_id")
            if action not in {"building_manager.list_pending"}
            else 0
        )
        if action == "building_manager.list_pending":
            return await self._workflow.list_pending_requirements(
                identity, _integer(value.get("page", 1), "page")
            )
        if action in {"building_manager.open_requirement", "building_manager.refresh"}:
            return await self._workflow.open_requirement(identity, requirement_id)
        if action == "building_manager.save_review_fields":
            raw = {
                name: event.form_values[name]
                for name in ReviewFieldsPatch.model_fields
                if name in event.form_values
            }
            if "proposed_supplier_id" in raw and raw["proposed_supplier_id"] not in ("", None):
                raw["proposed_supplier_id"] = int(str(raw["proposed_supplier_id"]))
            if "need_contract" in raw:
                raw["need_contract"] = raw["need_contract"] == "true"
            return await self._workflow.save_review_fields(
                identity,
                requirement_id,
                _integer(value.get("expected_version"), "expected_version"),
                ReviewFieldsPatch.model_validate(raw),
            )
        if action == "building_manager.prepare_reject":
            reason = event.form_values.get("reason")
            return await self._workflow.prepare_reject(
                identity, requirement_id, reason if isinstance(reason, str) else None
            )
        if action == "building_manager.confirm_reject":
            return await self._workflow.confirm_reject(
                identity,
                requirement_id,
                _integer(value.get("expected_version"), "expected_version"),
                str(value.get("reason", "")),
                UUID(str(value.get("action_token"))),
            )
        if action == "building_manager.prepare_submit_purchaser":
            employee = event.form_values.get("assigned_to_employee_id")
            return await self._workflow.prepare_submit_purchaser(
                identity,
                requirement_id,
                _integer(employee, "assigned_to_employee_id") if employee is not None else None,
            )
        if action == "building_manager.confirm_submit_purchaser":
            return await self._workflow.confirm_submit_purchaser(
                identity,
                requirement_id,
                _integer(value.get("expected_version"), "expected_version"),
                _integer(value.get("assigned_to_employee_id"), "assigned_to_employee_id"),
                UUID(str(value.get("action_token"))),
            )
        raise ValueError("unsupported building manager action")
