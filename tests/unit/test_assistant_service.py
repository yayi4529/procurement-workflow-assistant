# ruff: noqa: RUF001

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.assistant.agent_router import AgentRouter
from procurement_platform.application.assistant.agents.base import BasicRoleAgent
from procurement_platform.application.assistant.context_builder import AssistantContextBuilder
from procurement_platform.application.assistant.role_intent import (
    RoleIntentResolution,
    RoleIntentResolver,
)
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.service import AssistantService
from procurement_platform.application.assistant.session_service import AssistantSessionService
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.domain.assistant import (
    AssistantClarificationResponse,
    AssistantTextResponse,
    AssistantTurn,
)
from procurement_platform.domain.enums import PlatformType, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.inbound_event import TextMessageEvent
from procurement_platform.domain.user import CurrentUser, UserRole


class ApplicantStub(BasicRoleAgent):
    role = RoleCode.APPLICANT
    role_prompt = "applicant"
    tool_names = frozenset()


class PurchaserStub(BasicRoleAgent):
    role = RoleCode.PURCHASER
    role_prompt = "purchaser"
    tool_names = frozenset()


class BuildingManagerStub(BasicRoleAgent):
    role = RoleCode.BUILDING_MANAGER
    role_prompt = "building manager"
    tool_names = frozenset()


class StubRoleIntentResolver:
    def __init__(
        self, resolution: RoleIntentResolution | None = None, *, fail: bool = False
    ) -> None:
        self.resolution = resolution
        self.fail = fail
        self.calls: list[tuple[tuple[RoleCode, ...], RoleCode]] = []

    async def resolve(
        self,
        *,
        user_text: str,
        allowed_roles: tuple[RoleCode, ...],
        focused_role: RoleCode,
    ) -> RoleIntentResolution:
        del user_text
        self.calls.append((allowed_roles, focused_role))
        if self.fail:
            raise RuntimeError("resolver failed")
        assert self.resolution is not None
        return self.resolution


def service(
    backend: FakeBackendClient,
    *,
    resolver: RoleIntentResolver | None = None,
    turns: tuple[AssistantTurn, ...] = (),
) -> AssistantService:
    sessions = AssistantSessionService(backend)
    registry = ToolRegistry()
    executor = ToolExecutor(registry, max_result_chars=1000)
    runtime = AssistantRuntime(
        llm_client=FakeLlmClient(turns=turns),
        tool_registry=registry,
        tool_executor=executor,
        tool_policy=ToolPolicy(),
        max_tool_steps=2,
    )
    return AssistantService(
        backend_client=backend,
        session_service=sessions,
        context_builder=AssistantContextBuilder(),
        agent_router=AgentRouter(
            (ApplicantStub(sessions), BuildingManagerStub(sessions), PurchaserStub(sessions))
        ),
        runtime=runtime,
        max_history_messages=20,
        role_intent_resolver=resolver,
    )


def event(identifier: str, text: str) -> TextMessageEvent:
    return TextMessageEvent(
        event_id=f"event-{identifier}",
        external_user_id="ou_multi",
        external_message_id=identifier,
        chat_id="chat",
        text=text,
    )


@pytest.mark.asyncio
async def test_multi_role_selection_is_explicit_and_persisted() -> None:
    backend = FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="Multi",
            mobile=None,
            status="ACTIVE",
            roles=(
                UserRole(role_code=RoleCode.APPLICANT, role_name="Applicant"),
                UserRole(role_code=RoleCode.PURCHASER, role_name="Purchaser"),
            ),
            buildings=(),
        )
    )
    assistant = service(backend)

    first = await assistant.handle(event("m1", "帮我处理采购"))
    second = await assistant.handle(event("m2", "2"))

    assert isinstance(first, AssistantClarificationResponse)
    assert [option.value for option in first.options] == ["APPLICANT", "PURCHASER"]
    assert second == AssistantTextResponse(text="已选择采购员助手，请继续告诉我需要处理的内容。")
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_multi")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.focused_role is RoleCode.PURCHASER

    switched = await assistant.handle(event("m3", "切换角色 需求人"))
    assert switched == AssistantTextResponse(
        text="已切换到需求人助手，请继续告诉我需要处理的内容。"
    )
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.focused_role is RoleCode.APPLICANT


def multi_role_backend() -> FakeBackendClient:
    return FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="Multi",
            mobile=None,
            status="ACTIVE",
            roles=(
                UserRole(role_code=RoleCode.APPLICANT),
                UserRole(role_code=RoleCode.BUILDING_MANAGER),
            ),
            buildings=(),
        )
    )


async def choose_role(assistant: AssistantService, role_index: int = 1) -> None:
    await assistant.handle(event("select-prompt", "开始处理"))
    await assistant.handle(event("select-role", str(role_index)))


@pytest.mark.asyncio
async def test_single_role_never_calls_semantic_resolver() -> None:
    backend = FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="Applicant",
            mobile=None,
            status="ACTIVE",
            roles=(UserRole(role_code=RoleCode.APPLICANT),),
            buildings=(),
        )
    )
    resolver = StubRoleIntentResolver(RoleIntentResolution(RoleCode.APPLICANT, "HIGH"))
    assistant = service(backend, resolver=resolver, turns=(AssistantTurn(content="已处理"),))

    assert await assistant.handle(event("single", "帮我采购")) == AssistantTextResponse(
        text="已处理"
    )
    assert resolver.calls == []


@pytest.mark.asyncio
async def test_explicit_switch_has_priority_over_semantic_resolver() -> None:
    backend = multi_role_backend()
    resolver = StubRoleIntentResolver(RoleIntentResolution(RoleCode.APPLICANT, "HIGH"))
    assistant = service(backend, resolver=resolver)
    await choose_role(assistant)

    response = await assistant.handle(event("explicit", "切换到楼长"))

    assert response == AssistantTextResponse(text="已切换到楼长助手，请继续告诉我需要处理的内容。")
    assert resolver.calls == []


@pytest.mark.asyncio
async def test_high_confidence_switches_to_authorized_role_and_persists() -> None:
    backend = multi_role_backend()
    resolver = StubRoleIntentResolver(RoleIntentResolution(RoleCode.BUILDING_MANAGER, "HIGH"))
    assistant = service(backend, resolver=resolver, turns=(AssistantTurn(content="楼长上下文"),))
    await choose_role(assistant)

    response = await assistant.handle(event("semantic-manager", "看一下有哪些待审核采购单"))

    assert response == AssistantTextResponse(text="楼长上下文")
    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_multi")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.focused_role is RoleCode.BUILDING_MANAGER


@pytest.mark.asyncio
async def test_high_confidence_switches_back_to_applicant() -> None:
    backend = multi_role_backend()
    resolver = StubRoleIntentResolver(RoleIntentResolution(RoleCode.APPLICANT, "HIGH"))
    assistant = service(backend, resolver=resolver, turns=(AssistantTurn(content="需求人上下文"),))
    await choose_role(assistant, role_index=2)

    await assistant.handle(event("semantic-applicant", "我还想新采购两台 UPS"))

    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_multi")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.focused_role is RoleCode.APPLICANT


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", (False, True))
async def test_unclear_or_failed_resolver_keeps_current_role(fail: bool) -> None:
    backend = multi_role_backend()
    resolver = StubRoleIntentResolver(
        RoleIntentResolution(RoleCode.BUILDING_MANAGER, "LOW"), fail=fail
    )
    assistant = service(backend, resolver=resolver, turns=(AssistantTurn(content="保持"),))
    await choose_role(assistant)

    await assistant.handle(event(f"keep-{fail}", "看看这单"))

    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_multi")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.focused_role is RoleCode.APPLICANT


@pytest.mark.asyncio
async def test_unauthorized_resolver_role_is_rejected_by_router() -> None:
    backend = multi_role_backend()
    resolver = StubRoleIntentResolver(RoleIntentResolution(RoleCode.PURCHASER, "HIGH"))
    assistant = service(backend, resolver=resolver, turns=(AssistantTurn(content="保持"),))
    await choose_role(assistant)

    await assistant.handle(event("unauthorized", "帮我处理采购执行"))

    identity = PlatformIdentity.create(PlatformType.FEISHU, "ou_multi")
    conversation = await backend.get_or_create_agent_conversation(
        identity=identity, current_action="ASSISTANT_CHAT"
    )
    state = await backend.get_agent_state(
        identity=identity, conversation_id=conversation.conversation_id
    )
    assert state.focused_role is RoleCode.APPLICANT
