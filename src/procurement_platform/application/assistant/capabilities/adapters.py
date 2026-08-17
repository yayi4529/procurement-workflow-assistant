from typing import Generic, TypeVar

from pydantic import BaseModel

from procurement_platform.application.assistant.capabilities.metadata import CapabilityMetadata
from procurement_platform.application.assistant.tools import AssistantTool, ToolSideEffect
from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult

ArgsT = TypeVar("ArgsT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=AssistantToolResult)


class ExistingToolCapabilityAdapter(Generic[ArgsT, ResultT]):
    """Adds capability metadata without changing an existing tool's execution contract."""

    def __init__(
        self,
        tool: AssistantTool[ArgsT, ResultT],
        metadata: CapabilityMetadata,
    ) -> None:
        if tool.name != metadata.name:
            raise ValueError(f"capability metadata name does not match tool: {tool.name}")
        if tool.description != metadata.description:
            raise ValueError(f"capability metadata description does not match tool: {tool.name}")
        if tool.side_effect != metadata.side_effect:
            raise ValueError(f"capability metadata side effect does not match tool: {tool.name}")
        self._tool = tool
        self._metadata = metadata

    @property
    def metadata(self) -> CapabilityMetadata:
        return self._metadata

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def description(self) -> str:
        return self._tool.description

    @property
    def args_model(self) -> type[ArgsT]:
        return self._tool.args_model

    @property
    def side_effect(self) -> ToolSideEffect:
        return self._tool.side_effect

    async def execute(self, *, args: ArgsT, context: AssistantToolContext) -> ResultT:
        return await self._tool.execute(args=args, context=context)
