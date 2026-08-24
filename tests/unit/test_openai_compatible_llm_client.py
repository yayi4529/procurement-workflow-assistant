from collections import deque
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from procurement_platform.adapters.llm.openai_compatible_llm_client import (
    OpenAICompatibleLlmClient,
)
from procurement_platform.domain.assistant_errors import (
    LlmAuthenticationError,
    LlmBadRequestError,
    LlmInvalidResponseError,
    LlmProviderError,
    LlmRateLimitError,
    LlmTimeoutError,
)


def _error(name: str, *, status_code: int | None = None, message: str = "failure") -> Exception:
    error_type = type(name, (Exception,), {})
    error = error_type(message)
    error.status_code = status_code  # type: ignore[attr-defined]
    return error


def _response(content: str | None = "ok", *, choices: bool = True) -> SimpleNamespace:
    values = (
        [SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]))]
        if choices
        else []
    )
    return SimpleNamespace(choices=values)


class _Completions:
    def __init__(self, outcomes: tuple[object, ...]) -> None:
        self.outcomes = deque(outcomes)
        self.requests: list[dict[str, object]] = []

    async def create(self, **request: object) -> object:
        self.requests.append(request)
        outcome = self.outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _SdkClient:
    def __init__(self, outcomes: tuple[object, ...]) -> None:
        self.chat = SimpleNamespace(completions=_Completions(outcomes))
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _client(
    outcomes: tuple[object, ...], *, sleeps: list[float] | None = None
) -> tuple[OpenAICompatibleLlmClient, _SdkClient, list[dict[str, object]]]:
    sdk = _SdkClient(outcomes)
    factory_calls: list[dict[str, object]] = []

    def factory(**kwargs: object) -> _SdkClient:
        factory_calls.append(kwargs)
        return sdk

    async def sleep(delay: float) -> None:
        if sleeps is not None:
            sleeps.append(delay)

    client = OpenAICompatibleLlmClient(
        api_key=SecretStr("secret"),
        model="test",
        timeout_seconds=1,
        max_attempts=3,
        backoff_base_seconds=0,
        client_factory=factory,
        sleep=sleep,
    )
    return client, sdk, factory_calls


@pytest.mark.asyncio
async def test_sdk_client_is_reused_and_closed() -> None:
    client, sdk, factory_calls = _client((_response("one"), _response("two")))
    assert (await client.complete(messages=(), tools=())).content == "one"
    assert (await client.complete(messages=(), tools=())).content == "two"
    await client.aclose()
    assert len(factory_calls) == 1
    assert sdk.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_error("RateLimitError", status_code=429), LlmRateLimitError),
        (_error("InternalServerError", status_code=500), LlmProviderError),
        (_error("APITimeoutError"), LlmTimeoutError),
    ],
)
async def test_transient_errors_retry_then_preserve_typed_error(
    error: Exception, expected: type[Exception]
) -> None:
    sleeps: list[float] = []
    client, sdk, _ = _client((error, error, error), sleeps=sleeps)
    with pytest.raises(expected):
        await client.complete(messages=(), tools=())
    assert len(sdk.chat.completions.requests) == 3
    assert len(sleeps) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_error("AuthenticationError", status_code=401), LlmAuthenticationError),
        (_error("BadRequestError", status_code=400), LlmBadRequestError),
    ],
)
async def test_permanent_errors_do_not_retry(error: Exception, expected: type[Exception]) -> None:
    client, sdk, _ = _client((error,))
    with pytest.raises(expected):
        await client.complete(messages=(), tools=())
    assert len(sdk.chat.completions.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "Thinking mode does not support this tool_choice",
        "Invalid parameter: tool_choice",
    ),
)
async def test_tool_choice_bad_request_falls_back_once(message: str) -> None:
    unsupported = _error(
        "BadRequestError",
        status_code=400,
        message=message,
    )
    client, sdk, _ = _client((unsupported, _response()))
    result = await client.complete(messages=(), tools=(), tool_choice="required")
    assert result.content == "ok"
    assert "tool_choice" in sdk.chat.completions.requests[0]
    assert "tool_choice" not in sdk.chat.completions.requests[1]


@pytest.mark.asyncio
async def test_tool_choice_fallback_is_available_with_one_normal_attempt() -> None:
    unsupported = _error("BadRequestError", status_code=400)
    client, sdk, _ = _client((unsupported, _response()))
    client._max_attempts = 1

    result = await client.complete(messages=(), tools=(), tool_choice="required")

    assert result.content == "ok"
    assert len(sdk.chat.completions.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [_response(choices=False), _response(content=None)])
async def test_invalid_provider_responses_are_rejected(response: SimpleNamespace) -> None:
    client, _, _ = _client((response, response, response))
    with pytest.raises(LlmInvalidResponseError):
        await client.complete(messages=(), tools=())


@pytest.mark.asyncio
async def test_empty_provider_response_retries_then_recovers() -> None:
    client, sdk, _ = _client((_response(content=None), _response("recovered")))

    result = await client.complete(messages=(), tools=())

    assert result.content == "recovered"
    assert len(sdk.chat.completions.requests) == 2
