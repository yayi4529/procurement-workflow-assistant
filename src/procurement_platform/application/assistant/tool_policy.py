from procurement_platform.application.assistant.capabilities.catalog import (
    DEFAULT_CAPABILITY_METADATA,
)
from procurement_platform.application.assistant.capabilities.policy import CapabilityPolicy
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser


class ToolPolicy:
    """Compatibility facade over CapabilityPolicy for the current role-based runtime."""

    def __init__(
        self,
        capability_policy: CapabilityPolicy | None = None,
        *,
        allow_fake_tools: bool = False,
    ) -> None:
        self._capability_policy = capability_policy or CapabilityPolicy(DEFAULT_CAPABILITY_METADATA)
        self._allow_fake_tools = allow_fake_tools

    def allowed_tool_names(
        self, *, current_user: CurrentUser, active_role: RoleCode
    ) -> frozenset[str]:
        roles = {item.role_code for item in current_user.roles}
        names: set[str] = set()
        if current_user.status == "ACTIVE" and active_role in roles:
            names.update(self._capability_policy.allowed_names_for_roles({active_role}))
        if self._allow_fake_tools:
            names.add("echo_tool")
        return frozenset(names)
