import pytest

from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.assistant.role_intent import LlmRoleIntentResolver
from procurement_platform.domain.assistant import AssistantTurn
from procurement_platform.domain.enums import RoleCode


@pytest.mark.asyncio
async def test_role_intent_maps_only_authorized_selection_index() -> None:
    llm = FakeLlmClient(turns=(AssistantTurn(content='{"selection_index":2,"confidence":"HIGH"}'),))
    resolver = LlmRoleIntentResolver(llm)

    result = await resolver.resolve(
        user_text="看一下有哪些待审核采购单",
        allowed_roles=(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER),
        focused_role=RoleCode.APPLICANT,
    )

    assert result.role is RoleCode.BUILDING_MANAGER
    assert result.confidence == "HIGH"
    system_message = llm.calls[0][0].content or ""
    assert "APPLICANT" in system_message
    assert "BUILDING_MANAGER" in system_message
    assert "PURCHASER" not in system_message
    assert "WAREHOUSE_MANAGER" not in system_message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    (
        '{"selection_index":3,"confidence":"HIGH"}',
        '{"selection_index":1,"confidence":"UNKNOWN"}',
        "not-json",
    ),
)
async def test_role_intent_invalid_output_keeps_focused_role(content: str) -> None:
    resolver = LlmRoleIntentResolver(FakeLlmClient(turns=(AssistantTurn(content=content),)))

    result = await resolver.resolve(
        user_text="看看这单",
        allowed_roles=(RoleCode.APPLICANT, RoleCode.BUILDING_MANAGER),
        focused_role=RoleCode.APPLICANT,
    )

    assert result.role is RoleCode.APPLICANT
    assert result.confidence == "LOW"


@pytest.mark.asyncio
async def test_single_role_does_not_call_llm() -> None:
    llm = FakeLlmClient(turns=())
    resolver = LlmRoleIntentResolver(llm)

    result = await resolver.resolve(
        user_text="帮我审批",
        allowed_roles=(RoleCode.APPLICANT,),
        focused_role=RoleCode.APPLICANT,
    )

    assert result.role is RoleCode.APPLICANT
    assert llm.calls == []
