from procurement_platform.domain.requirement import RequirementDetail
from procurement_platform.domain.user import CurrentUser


class ToolPolicy:
    def __init__(self, *, allow_fake_tools: bool = False) -> None:
        self._allow_fake_tools = allow_fake_tools

    def allowed_tool_names(
        self, *, current_user: CurrentUser, active_requirement: RequirementDetail | None
    ) -> frozenset[str]:
        del current_user, active_requirement
        return frozenset({"echo_tool"}) if self._allow_fake_tools else frozenset()
