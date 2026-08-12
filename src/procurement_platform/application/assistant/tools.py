import json
import logging
from typing import Generic, Protocol, TypeVar, cast

from pydantic import BaseModel, ValidationError

from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantToolContext,
    AssistantToolDefinition,
    AssistantToolResult,
)
from procurement_platform.domain.assistant_errors import (
    AssistantToolArgumentsError,
    UnknownAssistantToolError,
)

ArgsT = TypeVar("ArgsT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=AssistantToolResult, covariant=True)

logger = logging.getLogger(__name__)


class AssistantTool(Protocol, Generic[ArgsT, ResultT]):
    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def args_model(self) -> type[ArgsT]: ...

    async def execute(self, *, args: ArgsT, context: AssistantToolContext) -> ResultT: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AssistantTool[BaseModel, AssistantToolResult]] = {}

    def register(self, tool: AssistantTool[ArgsT, ResultT]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"assistant tool already registered: {tool.name}")
        self._tools[tool.name] = cast(AssistantTool[BaseModel, AssistantToolResult], tool)

    def get(self, name: str) -> AssistantTool[BaseModel, AssistantToolResult]:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise UnknownAssistantToolError("未知工具") from exc

    @property
    def registered_names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def definitions(self, *, allowed_names: frozenset[str]) -> tuple[AssistantToolDefinition, ...]:
        return tuple(
            AssistantToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.args_model.model_json_schema(),
            )
            for name, tool in self._tools.items()
            if name in allowed_names
        )


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, *, max_result_chars: int) -> None:
        self._registry = registry
        self._max_result_chars = max_result_chars

    async def execute(
        self,
        *,
        name: str,
        arguments_json: str,
        tool_call_id: str,
        context: AssistantToolContext,
        allowed_names: frozenset[str],
    ) -> AssistantMessage:
        message, _ = await self.execute_result(
            name=name,
            arguments_json=arguments_json,
            tool_call_id=tool_call_id,
            context=context,
            allowed_names=allowed_names,
        )
        return message

    async def execute_result(
        self,
        *,
        name: str,
        arguments_json: str,
        tool_call_id: str,
        context: AssistantToolContext,
        allowed_names: frozenset[str],
    ) -> tuple[AssistantMessage, AssistantToolResult]:
        if name not in allowed_names:
            result = AssistantToolResult(
                status="PERMISSION_DENIED", user_message="当前不可使用该工具"
            )
        else:
            try:
                tool = self._registry.get(name)
                value = json.loads(arguments_json)
                if not isinstance(value, dict):
                    raise AssistantToolArgumentsError("工具参数必须是 JSON 对象")
                args = tool.args_model.model_validate(value)
                result = await tool.execute(args=args, context=context)
            except (json.JSONDecodeError, ValidationError, AssistantToolArgumentsError):
                result = AssistantToolResult(
                    status="INVALID_ARGUMENTS", user_message="工具参数无效"
                )
            except UnknownAssistantToolError:
                result = AssistantToolResult(status="NOT_FOUND", user_message="未知工具")
            except Exception:
                logger.exception("Assistant tool execution failed", extra={"tool_name": name})
                result = AssistantToolResult(status="INTERNAL_ERROR", user_message="工具暂时不可用")
        content = result.model_dump_json()
        if len(content) > self._max_result_chars:
            content = content[: self._max_result_chars]
        return (
            AssistantMessage(role="tool", name=name, tool_call_id=tool_call_id, content=content),
            result,
        )
