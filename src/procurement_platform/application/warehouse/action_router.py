from uuid import UUID

from procurement_platform.application.warehouse.workflow_service import WarehouseWorkflowService
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import CardInteractionEvent
from procurement_platform.domain.interaction import InteractionView
from procurement_platform.domain.json_types import JsonValue
from procurement_platform.domain.requirement import WarehouseFieldsPatch


def _integer(value: JsonValue | None, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} is required")
    return int(value)


class WarehouseActionRouter:
    def __init__(self, workflow: WarehouseWorkflowService) -> None:
        self._workflow = workflow

    async def route(self, event: CardInteractionEvent) -> InteractionView:
        identity = PlatformIdentity.create(PlatformType.FEISHU, event.external_user_id)
        value, action = event.action_value, event.action_id
        if action == "warehouse.list_pending":
            return await self._workflow.list_pending(identity)
        requirement_id = _integer(value.get("requirement_id"), "requirement_id")
        if action in {"warehouse.open_requirement", "warehouse.refresh"}:
            return await self._workflow.open_requirement(identity, requirement_id)
        if action == "warehouse.save_fields":
            raw = {
                name: event.form_values[name]
                for name in WarehouseFieldsPatch.model_fields
                if name in event.form_values
            }
            return await self._workflow.save_warehouse_fields(
                identity,
                requirement_id,
                _integer(value.get("expected_version"), "expected_version"),
                WarehouseFieldsPatch.model_validate(raw),
            )
        if action == "warehouse.prepare_complete":
            return await self._workflow.prepare_complete(identity, requirement_id)
        if action == "warehouse.confirm_complete":
            return await self._workflow.confirm_complete(
                identity,
                requirement_id,
                _integer(value.get("expected_version"), "expected_version"),
                UUID(str(value.get("action_token"))),
            )
        raise ValueError("unsupported warehouse action")
