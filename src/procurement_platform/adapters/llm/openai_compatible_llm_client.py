import asyncio
import inspect
import logging
import random
from collections.abc import Awaitable, Callable
from importlib import import_module
from typing import Any

from pydantic import SecretStr

from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantToolCall,
    AssistantToolDefinition,
    AssistantTurn,
)
from procurement_platform.domain.assistant_errors import (
    AssistantError,
    LlmAuthenticationError,
    LlmBadRequestError,
    LlmInvalidResponseError,
    LlmProviderError,
    LlmRateLimitError,
    LlmTimeoutError,
    LlmUnavailableError,
)

logger = logging.getLogger(__name__)


class OpenAICompatibleLlmClient:
    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float,
        base_url: str | None = None,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.25,
        client_factory: Callable[..., Any] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._model = model
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds
        self._sleep = sleep
        try:
            factory = client_factory or import_module("openai").AsyncOpenAI
            self._client: Any = factory(
                api_key=api_key.get_secret_value(),
                base_url=base_url,
                timeout=timeout_seconds,
            )
        except ImportError as exc:
            raise LlmUnavailableError("OpenAI SDK is unavailable") from exc

    async def complete(
        self,
        *,
        messages: tuple[AssistantMessage, ...],
        tools: tuple[AssistantToolDefinition, ...],
        tool_choice: str | None = None,
    ) -> AssistantTurn:
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
        if tool_choice is not None:
            request["tool_choice"] = tool_choice
        invalid_reason = "LLM returned invalid response"
        for attempt in range(1, self._max_attempts + 1):
            response = await self._create_with_retry(request)
            if not response.choices:
                invalid_reason = "LLM returned no choices"
            else:
                message = response.choices[0].message
                calls = tuple(
                    AssistantToolCall(
                        id=call.id,
                        name=call.function.name,
                        arguments_json=call.function.arguments,
                    )
                    for call in message.tool_calls or ()
                    if hasattr(call, "function")
                )
                if (message.content and message.content.strip()) or calls:
                    return AssistantTurn(content=message.content, tool_calls=calls)
                invalid_reason = "LLM returned empty response"
            if attempt < self._max_attempts:
                logger.warning("assistant.llm.empty_response_retry", extra={"attempt": attempt})
        raise LlmInvalidResponseError(invalid_reason)

    async def _create_with_retry(self, request: dict[str, object]) -> Any:
        fallback_used = False
        attempt = 0
        while attempt < self._max_attempts:
            attempt += 1
            try:
                return await self._client.chat.completions.create(**request)
            except Exception as exc:
                if (
                    not fallback_used
                    and "tool_choice" in request
                    and self._tool_choice_may_be_unsupported(exc)
                ):
                    fallback_used = True
                    request = dict(request)
                    request.pop("tool_choice", None)
                    attempt -= 1
                    logger.info("assistant.llm.tool_choice_fallback", extra={"attempt": attempt})
                    continue
                mapped, transient = self._classify(exc)
                if not transient or attempt >= self._max_attempts:
                    raise mapped from exc
                delay = self._backoff_base_seconds * (2 ** (attempt - 1))
                delay += random.uniform(0, self._backoff_base_seconds)
                logger.warning(
                    "assistant.llm.retry",
                    extra={"attempt": attempt, "error_type": type(mapped).__name__},
                )
                await self._sleep(delay)
        raise LlmUnavailableError("LLM retry policy exhausted")

    @staticmethod
    def _classify(exc: Exception) -> tuple[AssistantError, bool]:
        name = exc.__class__.__name__
        status = getattr(exc, "status_code", None)
        if name in {"APITimeoutError", "TimeoutError"}:
            return LlmTimeoutError("LLM request timed out"), True
        if name == "RateLimitError" or status == 429:
            return LlmRateLimitError("LLM rate limit exceeded"), True
        if name in {"AuthenticationError", "PermissionDeniedError"} or status in {401, 403}:
            return LlmAuthenticationError("LLM authentication or authorization failed"), False
        if name == "BadRequestError" or status in {400, 422}:
            return LlmBadRequestError("LLM rejected the request"), False
        if name == "APIConnectionError":
            return LlmUnavailableError("LLM connection unavailable"), True
        if name == "InternalServerError" or (isinstance(status, int) and status >= 500):
            return LlmProviderError("LLM provider failed"), True
        return LlmUnavailableError("LLM request failed"), False

    async def aclose(self) -> None:
        close = getattr(self._client, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result

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
    def _tool_choice_may_be_unsupported(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        return exc.__class__.__name__ == "BadRequestError" or status in {400, 422}
