from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

from procurement_platform.application.assistant.capabilities.metadata import CapabilityMetadata
from procurement_platform.application.assistant.tools import AssistantTool
from procurement_platform.domain.assistant import AssistantToolResult

ArgsT = TypeVar("ArgsT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=AssistantToolResult, covariant=True)


class Capability(AssistantTool[ArgsT, ResultT], Protocol, Generic[ArgsT, ResultT]):
    """An existing executable tool enriched with agent-facing authorization metadata."""

    @property
    def metadata(self) -> CapabilityMetadata: ...
