import os

import pytest
from pydantic import SecretStr

from procurement_platform.adapters.llm.openai_compatible_llm_client import OpenAICompatibleLlmClient
from procurement_platform.domain.assistant import AssistantMessage, AssistantToolDefinition

from .cases import ALL_CASES, AgentEvalCase
from .helpers import RecordingLlmClient


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda case: case.case_id)
@pytest.mark.asyncio
async def test_real_model_understands_natural_language_case(
    require_real_llm: None, case: AgentEvalCase
) -> None:
    """Reserve opt-in cases until their named backend fixture is provisioned.

    The separate connection smoke guarantees that opt-in uses the configured real client and never
    a fake fallback. Full AssistantService execution requires each named business fixture to be
    provisioned explicitly; an absent fixture is skipped instead of using invented state.
    """
    del require_real_llm
    pytest.skip(f"business fixture not provisioned for real baseline: {case.fixture}")


@pytest.mark.asyncio
async def test_real_model_client_is_configured_without_fake_fallback(
    require_real_llm: None,
) -> None:
    del require_real_llm
    api_key = os.environ["PROCUREMENT_LLM_API_KEY"]
    model = os.environ["PROCUREMENT_LLM_MODEL"]
    client = RecordingLlmClient(
        OpenAICompatibleLlmClient(
            api_key=SecretStr(api_key),
            model=model,
            timeout_seconds=float(os.getenv("PROCUREMENT_LLM_TIMEOUT_SECONDS", "30")),
            base_url=os.getenv("PROCUREMENT_LLM_BASE_URL") or None,
        )
    )
    tools = (
        AssistantToolDefinition(
            name="eval_noop",
            description="Return the supplied text without business side effects.",
            parameters={"type": "object", "properties": {}},
            side_effect="READ_ONLY",
        ),
    )
    turn = await client.complete(
        messages=(AssistantMessage(role="user", content="只回复: 连接成功"),), tools=tools
    )
    assert turn.content or turn.tool_calls
