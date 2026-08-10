from dataclasses import dataclass

from procurement_platform.application.assistant.agent_router import (
    AgentRouter,
    RoleSelectionRequired,
)
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantResponse,
    AssistantToolCall,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.assistant_session import AgentSessionState
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser, UserRole


@dataclass
class StubAgent:
    role: RoleCode

    def allowed_tool_names(self) -> frozenset[str]:
        return frozenset()

    def allowed_tool_names_for(self, user_text: str) -> frozenset[str]:
        del user_text
        return frozenset()

    def retry_tool_name(self) -> str | None:
        return None

    def prepare_tool_call(self, call: AssistantToolCall, *, user_text: str) -> AssistantToolCall:
        del user_text
        return call

    def build_messages(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
    ) -> tuple[AssistantMessage, ...]:
        del context
        return history

    async def before_run(
        self,
        *,
        context: AssistantToolContext,
        history: tuple[AssistantMessage, ...],
        user_text: str,
        external_message_id: str,
    ) -> AssistantResponse | None:
        del context, history, user_text, external_message_id
        return None

    async def handle_content(
        self,
        *,
        content: str,
        context: AssistantToolContext,
        user_text: str,
        external_message_id: str,
        retry_count: int,
    ) -> AssistantResponse | None:
        del content, context, user_text, external_message_id, retry_count
        return None

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        del result, context, external_message_id
        return None


def current_user(*roles: RoleCode) -> CurrentUser:
    return CurrentUser(
        employee_id=1,
        name="Test",
        mobile=None,
        status="ACTIVE",
        roles=tuple(UserRole(role_code=role, role_name=role.value) for role in roles),
        buildings=(),
    )


def state(role: RoleCode | None) -> AgentSessionState:
    return AgentSessionState(conversation_id=1, focused_role=role)


def test_single_role_resolves_without_guessing() -> None:
    applicant = StubAgent(RoleCode.APPLICANT)
    router = AgentRouter((applicant,))

    assert router.resolve(current_user=current_user(RoleCode.APPLICANT), state=None) is applicant


def test_focused_role_selects_one_agent_for_multi_role_user() -> None:
    applicant = StubAgent(RoleCode.APPLICANT)
    purchaser = StubAgent(RoleCode.PURCHASER)
    router = AgentRouter((applicant, purchaser))

    result = router.resolve(
        current_user=current_user(RoleCode.APPLICANT, RoleCode.PURCHASER),
        state=state(RoleCode.PURCHASER),
    )

    assert result is purchaser


def test_invalid_focus_and_missing_focus_require_role_selection() -> None:
    router = AgentRouter((StubAgent(RoleCode.APPLICANT), StubAgent(RoleCode.PURCHASER)))
    user = current_user(RoleCode.APPLICANT, RoleCode.PURCHASER)

    invalid = router.resolve(current_user=user, state=state(RoleCode.BUILDING_MANAGER))
    missing = router.resolve(current_user=user, state=None)

    assert isinstance(invalid, RoleSelectionRequired)
    assert isinstance(missing, RoleSelectionRequired)
    assert missing.roles == (RoleCode.APPLICANT, RoleCode.PURCHASER)


def test_role_selection_accepts_only_available_exact_choice() -> None:
    router = AgentRouter((StubAgent(RoleCode.APPLICANT), StubAgent(RoleCode.PURCHASER)))
    roles = (RoleCode.APPLICANT, RoleCode.PURCHASER)

    assert router.selected_role("2", roles) is RoleCode.PURCHASER
    assert router.selected_role("切换角色 采购员", roles) is RoleCode.PURCHASER
    assert router.selected_role("楼长", roles) is None
