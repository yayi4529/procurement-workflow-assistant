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
ToolSideEffect = str


class AssistantTool(Protocol, Generic[ArgsT, ResultT]):
    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def args_model(self) -> type[ArgsT]: ...

    @property
    def side_effect(self) -> ToolSideEffect: ...

    async def execute(self, *, args: ArgsT, context: AssistantToolContext) -> ResultT: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AssistantTool[BaseModel, AssistantToolResult]] = {}

    def register(self, tool: AssistantTool[ArgsT, ResultT]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"assistant tool already registered: {tool.name}")
        if tool.side_effect not in {"READ", "MUTATE"}:
            raise ValueError(f"assistant tool has invalid side effect: {tool.name}")
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
                side_effect=tool.side_effect,
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
        payload = result.model_dump(mode="json")
        content = json.dumps(
            _compact_observation(payload, self._max_result_chars),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            AssistantMessage(role="tool", name=name, tool_call_id=tool_call_id, content=content),
            result,
        )


def _compact_observation(payload: object, max_chars: int) -> object:
    """Keep observations valid JSON while reducing oversized nested values."""
    compact = _compact_value(payload, list_limit=12, string_limit=400)
    if len(json.dumps(compact, ensure_ascii=False, separators=(",", ":"))) <= max_chars:
        return compact
    if isinstance(payload, dict):
        minimal = {
            key: payload[key]
            for key in (
                "status",
                "requirement_id",
                "updated_fields",
                "missing_fields",
                "next_missing_field",
                "fields_complete",
                "user_message",
                "total_count",
            )
            if key in payload
        }
        minimal["truncated"] = True
        return minimal
    return {"status": "SUCCESS", "truncated": True}


def _compact_value(value: object, *, list_limit: int, string_limit: int) -> object:
    if isinstance(value, str):
        return value if len(value) <= string_limit else value[:string_limit] + "…"
    if isinstance(value, list):
        return [
            _compact_value(item, list_limit=list_limit, string_limit=string_limit)
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        return {
            key: _compact_value(item, list_limit=list_limit, string_limit=string_limit)
            for key, item in value.items()
        }
    return value
