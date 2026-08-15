from collections.abc import Iterator
from typing import TypeVar, cast

from pydantic import BaseModel

from procurement_platform.application.assistant.capabilities.base import Capability
from procurement_platform.application.assistant.capabilities.metadata import CapabilityMetadata
from procurement_platform.application.assistant.tools import ToolRegistry
from procurement_platform.domain.assistant import AssistantToolResult

ArgsT = TypeVar("ArgsT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=AssistantToolResult, covariant=True)


class DuplicateCapabilityError(ValueError):
    pass


class UnknownCapabilityError(LookupError):
    pass


class CapabilityRegistry:
    """Ordered capability catalog backed by the existing executable ToolRegistry."""

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability[BaseModel, AssistantToolResult]] = {}
        self._tool_registry = ToolRegistry()

    def register(self, capability: Capability[ArgsT, ResultT]) -> None:
        if capability.name in self._capabilities:
            raise DuplicateCapabilityError(
                f"assistant capability already registered: {capability.name}"
            )
        stored = cast(Capability[BaseModel, AssistantToolResult], capability)
        self._tool_registry.register(stored)
        self._capabilities[capability.name] = stored

    def get(self, name: str) -> Capability[BaseModel, AssistantToolResult]:
        try:
            return self._capabilities[name]
        except KeyError as exc:
            raise UnknownCapabilityError(f"unknown assistant capability: {name}") from exc

    def all(self) -> tuple[Capability[BaseModel, AssistantToolResult], ...]:
        return tuple(self._capabilities.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._capabilities)

    def metadata(self) -> tuple[CapabilityMetadata, ...]:
        return tuple(capability.metadata for capability in self._capabilities.values())

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._tool_registry

    def __iter__(self) -> Iterator[Capability[BaseModel, AssistantToolResult]]:
        return iter(self._capabilities.values())
