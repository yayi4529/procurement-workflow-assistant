from collections.abc import Collection, Iterable

from procurement_platform.application.assistant.capabilities.metadata import CapabilityMetadata
from procurement_platform.application.assistant.capabilities.registry import CapabilityRegistry
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser


class CapabilityPolicy:
    """Role-only capability filtering; workflow state remains enforced by existing tools/backend."""

    def __init__(
        self,
        source: CapabilityRegistry | Iterable[CapabilityMetadata],
    ) -> None:
        metadata = source.metadata() if isinstance(source, CapabilityRegistry) else tuple(source)
        names = [item.name for item in metadata]
        if len(names) != len(set(names)):
            raise ValueError("duplicate capability metadata name")
        self._metadata = metadata

    def allowed_names_for_roles(self, roles: Collection[RoleCode]) -> frozenset[str]:
        role_set = frozenset(roles)
        return frozenset(
            item.name for item in self._metadata if item.allowed_roles.intersection(role_set)
        )

    def allowed_names_for(self, user: CurrentUser) -> frozenset[str]:
        if user.status != "ACTIVE":
            return frozenset()
        return self.allowed_names_for_roles(tuple(item.role_code for item in user.roles))

    def available_for(self, user: CurrentUser) -> tuple[CapabilityMetadata, ...]:
        allowed = self.allowed_names_for(user)
        return tuple(item for item in self._metadata if item.name in allowed)

    def side_effect_for(self, name: str) -> str | None:
        return next((item.side_effect for item in self._metadata if item.name == name), None)
