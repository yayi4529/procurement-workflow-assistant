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
        self, *, messages: tuple[AssistantMessage, ...], tools: tuple[AssistantToolDefinition, ...]
    ) -> AssistantTurn:
        try:
            client = import_module("openai").AsyncOpenAI(
                api_key=self._api_key.get_secret_value(),
                base_url=self._base_url,
                timeout=self._timeout_seconds,
            )
            response = await client.chat.completions.create(
                model=self._model,
                messages=[message.model_dump(exclude_none=True) for message in messages],
                tools=[
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
            )
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
