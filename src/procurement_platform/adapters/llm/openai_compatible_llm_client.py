from importlib import import_module

from pydantic import SecretStr

from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantToolCall,
    AssistantToolDefinition,
    AssistantTurn,
)
from procurement_platform.domain.assistant_errors import (
    LlmInvalidResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
)


class OpenAICompatibleLlmClient:
    def __init__(
        self, *, api_key: SecretStr, model: str, timeout_seconds: float, base_url: str | None = None
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url

    async def complete(
        self,
        *,
        messages: tuple[AssistantMessage, ...],
        tools: tuple[AssistantToolDefinition, ...],
        tool_choice: str | None = None,
    ) -> AssistantTurn:
        try:
            client = import_module("openai").AsyncOpenAI(
                api_key=self._api_key.get_secret_value(),
                base_url=self._base_url,
                timeout=self._timeout_seconds,
            )
            request: dict[str, object] = {
                "model": self._model,
                "messages": [self._message_payload(message) for message in messages],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        },
                    }
                    for tool in tools
                ]
                or None,
            }
            # Some OpenAI-compatible providers reject the presence of
            # ``tool_choice`` in thinking mode, even when its value is null.
            # Omit it unless the caller explicitly asks for a tool call.
            if tool_choice is not None:
                request["tool_choice"] = tool_choice
            try:
                response = await client.chat.completions.create(**request)
            except Exception as exc:
                if tool_choice is None or not self._tool_choice_is_unsupported(exc):
                    raise
                # Thinking-mode providers may support function tools but reject
                # the forced-choice extension. Retrying without it still lets
                # the model elect a tool call and keeps the turn responsive.
                request.pop("tool_choice", None)
                response = await client.chat.completions.create(**request)
        except ImportError as exc:
            raise LlmUnavailableError("OpenAI SDK is unavailable") from exc
        except Exception as exc:
            if exc.__class__.__name__ == "APITimeoutError":
                raise LlmTimeoutError("LLM request timed out") from exc
            raise LlmUnavailableError("LLM request failed") from exc
        if not response.choices:
            raise LlmInvalidResponseError("LLM returned no choices")
        message = response.choices[0].message
        calls = tuple(
            AssistantToolCall(
                id=call.id, name=call.function.name, arguments_json=call.function.arguments
            )
            for call in message.tool_calls or ()
            if hasattr(call, "function")
        )
        if not (message.content and message.content.strip()) and not calls:
            raise LlmInvalidResponseError("LLM returned empty response")
        return AssistantTurn(content=message.content, tool_calls=calls)

    @staticmethod
    def _message_payload(message: AssistantMessage) -> dict[str, object]:
        payload = message.model_dump(exclude_none=True, exclude={"tool_calls"})
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments_json},
                }
                for call in message.tool_calls
            ]
        return payload

    @staticmethod
    def _tool_choice_is_unsupported(exc: Exception) -> bool:
        return "thinking mode does not support this tool_choice" in str(exc).lower()
