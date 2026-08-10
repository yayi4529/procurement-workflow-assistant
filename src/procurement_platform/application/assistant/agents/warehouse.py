from procurement_platform.application.assistant.agents.base import BasicRoleAgent
from procurement_platform.application.assistant.prompts.warehouse import WAREHOUSE_PROMPT
from procurement_platform.domain.enums import RoleCode


class WarehouseAgent(BasicRoleAgent):
    role = RoleCode.WAREHOUSE_MANAGER
    role_prompt = WAREHOUSE_PROMPT
    tool_names = frozenset({"query_purchase_requests", "update_warehouse_receipt_draft"})
