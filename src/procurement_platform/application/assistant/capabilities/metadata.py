from dataclasses import dataclass

from procurement_platform.application.assistant.tools import ToolSideEffect
from procurement_platform.domain.enums import RoleCode


@dataclass(frozen=True, slots=True)
class CapabilityMetadata:
    name: str
    description: str
    side_effect: ToolSideEffect
    allowed_roles: frozenset[RoleCode]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("capability name must not be empty")
        if not self.description.strip():
            raise ValueError(f"capability description must not be empty: {self.name}")
        if self.side_effect not in {"READ", "MUTATE"}:
            raise ValueError(f"capability has invalid side effect: {self.name}")
        if not self.allowed_roles:
            raise ValueError(f"capability must allow at least one role: {self.name}")
