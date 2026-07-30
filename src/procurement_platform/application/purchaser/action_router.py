from uuid import UUID, uuid4

from procurement_platform.application.purchaser.workflow_service import PurchaserWorkflowService
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import CardInteractionEvent
from procurement_platform.domain.interaction import InteractionView
from procurement_platform.domain.json_types import JsonValue
from procurement_platform.domain.requirement import PurchaseFieldsPatch, SupplierUpsertCommand


def _integer(value: JsonValue | None, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} is required")
    return int(value)


class PurchaserActionRouter:
    def __init__(self, workflow: PurchaserWorkflowService) -> None:
        self._workflow = workflow

    async def route(self, event: CardInteractionEvent) -> InteractionView:
        identity = PlatformIdentity.create(PlatformType.FEISHU, event.external_user_id)
        value, action = event.action_value, event.action_id
        if action == "purchaser.list_pending":
            return await self._workflow.list_pending(identity)
        if action == "purchaser.search_supplier":
            keyword = event.form_values.get("keyword")
            if keyword is None:
                return self._workflow.prepare_supplier_search()
            return await self._workflow.search_supplier(identity, str(keyword))
        if action == "purchaser.select_supplier":
            return await self._workflow.select_supplier(
                identity, _integer(value.get("supplier_id"), "supplier_id")
            )
        if action == "purchaser.prepare_create_supplier":
            return self._workflow.prepare_new_supplier()
        if action == "purchaser.create_supplier":
            raw = {
                name: event.form_values[name]
                for name in SupplierUpsertCommand.model_fields
                if name in event.form_values
            }
            return await self._workflow.create_supplier(
                identity, SupplierUpsertCommand.model_validate(raw)
            )
        requirement_id = _integer(value.get("requirement_id"), "requirement_id")
        if action in {"purchaser.open_requirement", "purchaser.refresh"}:
            return await self._workflow.open_requirement(identity, requirement_id)
        if action == "purchaser.start_purchase":
            return await self._workflow.start_purchase(
                identity,
                requirement_id,
                _integer(value.get("expected_version"), "expected_version"),
                UUID(str(value.get("action_token") or uuid4())),
            )
        if action == "purchaser.save_purchase_fields":
            raw = {
                name: event.form_values[name]
                for name in PurchaseFieldsPatch.model_fields
                if name in event.form_values
            }
            if "supplier_id" in raw:
                raw["supplier_id"] = int(str(raw["supplier_id"]))
            if "update_supplier_profile" in raw:
                raw["update_supplier_profile"] = raw["update_supplier_profile"] == "true"
            return await self._workflow.save_purchase_fields(
                identity,
                requirement_id,
                _integer(value.get("expected_version"), "expected_version"),
                PurchaseFieldsPatch.model_validate(raw),
            )
        if action == "purchaser.prepare_submit_warehouse":
            employee = event.form_values.get("assigned_to_employee_id")
            return await self._workflow.prepare_submit_warehouse(
                identity,
                requirement_id,
                _integer(employee, "assigned_to_employee_id") if employee is not None else None,
            )
        if action == "purchaser.confirm_submit_warehouse":
            return await self._workflow.confirm_submit_warehouse(
                identity,
                requirement_id,
                _integer(value.get("expected_version"), "expected_version"),
                _integer(value.get("assigned_to_employee_id"), "assigned_to_employee_id"),
                UUID(str(value.get("action_token"))),
            )
        raise ValueError("unsupported purchaser action")
