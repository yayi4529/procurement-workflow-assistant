# ruff: noqa: RUF001

from dataclasses import dataclass

from procurement_platform.application.assistant.agents.protocol import RoleAgent
from procurement_platform.domain.assistant_session import AgentSessionState
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser

ROLE_LABELS: dict[RoleCode, str] = {
    RoleCode.APPLICANT: "需求人",
    RoleCode.BUILDING_MANAGER: "楼长",
    RoleCode.PURCHASER: "采购员",
    RoleCode.WAREHOUSE_MANAGER: "仓库管理员",
}


@dataclass(frozen=True, slots=True)
class RoleSelectionRequired:
    roles: tuple[RoleCode, ...]


class AgentRouter:
    def __init__(self, agents: tuple[RoleAgent, ...]) -> None:
        self._agents = {agent.role: agent for agent in agents}

    def resolve(
        self, *, current_user: CurrentUser, state: AgentSessionState | None
    ) -> RoleAgent | RoleSelectionRequired:
        supported = self.supported_roles(current_user)
        if state is not None and state.focused_role in supported:
            return self._agents[state.focused_role]
        if len(supported) == 1:
            return self._agents[supported[0]]
        return RoleSelectionRequired(roles=supported)

    def supported_roles(self, current_user: CurrentUser) -> tuple[RoleCode, ...]:
        user_roles = {item.role_code for item in current_user.roles}
        return tuple(role for role in ROLE_LABELS if role in user_roles and role in self._agents)

    def agent_for_role(self, *, current_user: CurrentUser, role: RoleCode) -> RoleAgent | None:
        if role not in self.supported_roles(current_user):
            return None
        return self._agents[role]

    def selected_role(self, text: str, roles: tuple[RoleCode, ...]) -> RoleCode | None:
        normalized = text.strip().rstrip("。.!！")
        for prefix in ("切换角色", "切换到"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :].strip(" ：:")
        if normalized.isdigit():
            index = int(normalized) - 1
            return roles[index] if 0 <= index < len(roles) else None
        for role in roles:
            if normalized in {ROLE_LABELS[role], role.value}:
                return role
        return None

    def agent(self, role: RoleCode) -> RoleAgent:
        return self._agents[role]
