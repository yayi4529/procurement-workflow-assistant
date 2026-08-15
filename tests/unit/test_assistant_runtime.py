import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ConfigDict

from procurement_platform.adapters.llm.echo_tool import EchoTool
from procurement_platform.adapters.llm.fake_llm_client import FakeLlmClient
from procurement_platform.application.assistant.grounding import (
    GroundingDecision,
    GroundingPolicy,
    GroundingRequirement,
)
from procurement_platform.application.assistant.runtime import AssistantRuntime
from procurement_platform.application.assistant.tool_policy import ToolPolicy
from procurement_platform.application.assistant.tools import ToolExecutor, ToolRegistry
from procurement_platform.application.assistant.turn_context import AgentTurnContext
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantResponse,
    AssistantTextResponse,
    AssistantToolCall,
    AssistantToolContext,
    AssistantToolResult,
    AssistantTurn,
)
from procurement_platform.domain.assistant_errors import (
    AssistantToolStepLimitError,
    LlmInvalidResponseError,
)
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser, UserRole


class MutateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class MutateResult(AssistantToolResult):
    pass


class LargeResult(AssistantToolResult):
    updated_fields: dict[str, object]
    missing_fields: list[str]


class MutateTool:
    args_model = MutateArgs
    description = "Test mutating tool."
    side_effect = "MUTATE"

    def __init__(self, name: str, calls: list[str]) -> None:
        self.name = name
        self._calls = calls

    async def execute(self, *, args: MutateArgs, context: AssistantToolContext) -> MutateResult:
        del context
        self._calls.append(args.value)
        return MutateResult(status="SUCCESS", user_message=args.value)


class ReadTool(MutateTool):
    side_effect = "READ"

    def __init__(self, name: str, calls: list[str], *, status: str = "SUCCESS") -> None:
        super().__init__(name, calls)
        self._status = status

    async def execute(self, *, args: MutateArgs, context: AssistantToolContext) -> MutateResult:
        del context
        self._calls.append(args.value)
        return MutateResult.model_validate({"status": self._status, "user_message": args.value})


class StubToolPolicy(ToolPolicy):
    def allowed_tool_names(
        self, *, current_user: CurrentUser, active_role: RoleCode
    ) -> frozenset[str]:
        del current_user, active_role
        return frozenset({"mutate_a", "mutate_b"})


@dataclass
class RuntimeAgent:
    response_to_tool: AssistantResponse | None
    role: RoleCode = RoleCode.APPLICANT
    tool_names: frozenset[str] = frozenset({"echo_tool"})
    results: list[AssistantToolResult] = field(default_factory=list)

    def allowed_tool_names(self) -> frozenset[str]:
        return frozenset({"echo_tool"})

    def allowed_tool_names_for(self, user_text: str) -> frozenset[str]:
        del user_text
        return self.allowed_tool_names()

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
        working_context: str | None = None,
    ) -> tuple[AssistantMessage, ...]:
        del context, working_context
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
        del context, user_text, external_message_id, retry_count
        return AssistantTextResponse(text=content)

    async def handle_tool_result(
        self,
        *,
        result: AssistantToolResult,
        context: AssistantToolContext,
        external_message_id: str,
    ) -> AssistantResponse | None:
        del context, external_message_id
        self.results.append(result)
        return self.response_to_tool


def runtime(
    turns: tuple[AssistantTurn, ...], *, max_steps: int = 3, max_total_calls: int = 24
) -> tuple[AssistantRuntime, FakeLlmClient]:
    registry = ToolRegistry()
    registry.register(EchoTool())
    llm = FakeLlmClient(turns=turns)
    executor = ToolExecutor(registry, max_result_chars=1000)
    return (
        AssistantRuntime(
            llm_client=llm,
            tool_registry=registry,
            tool_executor=executor,
            tool_policy=ToolPolicy(allow_fake_tools=True),
            max_tool_steps=max_steps,
            max_total_tool_calls=max_total_calls,
        ),
        llm,
    )


def context() -> AssistantToolContext:
    user = CurrentUser(
        employee_id=1,
        name="Test",
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=RoleCode.APPLICANT, role_name="Applicant"),),
        buildings=(),
    )
    return AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id="ou_test",
        conversation_id=1,
        external_conversation_id="chat",
        external_message_id="message",
        current_time=datetime.now(UTC),
        timezone_name="Asia/Shanghai",
        current_user=user,
    )


def turn_context() -> AgentTurnContext:
    tool_context = context()
    return AgentTurnContext(
        current_user=tool_context.current_user,
        active_role=RoleCode.APPLICANT,
        session_state=None,
        active_requirement=None,
        recent_history=(),
        current_recommendations=(),
        tool_context=tool_context,
    )


def echo_call(identifier: str) -> AssistantToolCall:
    return AssistantToolCall(id=identifier, name="echo_tool", arguments_json='{"text":"hello"}')


def read_call(identifier: str, name: str, value: str = "evidence") -> AssistantToolCall:
    return AssistantToolCall(id=identifier, name=name, arguments_json=json.dumps({"value": value}))


def grounded_runtime(
    turns: tuple[AssistantTurn, ...],
    *tools: ReadTool,
) -> tuple[AssistantRuntime, FakeLlmClient]:
    registry = ToolRegistry()
    registry.register(EchoTool())
    for tool in tools:
        registry.register(tool)
    llm = FakeLlmClient(turns=turns)
    return (
        AssistantRuntime(
            llm_client=llm,
            tool_registry=registry,
            tool_executor=ToolExecutor(registry, max_result_chars=1000),
            max_tool_steps=6,
        ),
        llm,
    )


@pytest.mark.asyncio
async def test_runtime_delegates_tool_result_and_returns_agent_response() -> None:
    engine, _ = runtime((AssistantTurn(tool_calls=(echo_call("one"),)),))
    agent = RuntimeAgent(response_to_tool=AssistantTextResponse(text="handled"))

    response = await engine.run(
        agent=agent,
        turn_context=turn_context(),
        user_text="hello",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="handled")
    assert len(agent.results) == 1


@pytest.mark.asyncio
async def test_runtime_puts_tool_message_back_and_continues() -> None:
    engine, llm = runtime(
        (AssistantTurn(tool_calls=(echo_call("one"),)), AssistantTurn(content="done"))
    )
    agent = RuntimeAgent(response_to_tool=None)

    response = await engine.run(
        agent=agent,
        turn_context=turn_context(),
        user_text="hello",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="done")
    assert llm.calls[1][-1].role == "tool"


@pytest.mark.asyncio
async def test_runtime_rejects_empty_llm_turn() -> None:
    engine, _ = runtime((AssistantTurn(),))

    with pytest.raises(LlmInvalidResponseError):
        await engine.run(
            agent=RuntimeAgent(response_to_tool=None),
            turn_context=turn_context(),
            user_text="hello",
            external_message_id="message",
        )


@pytest.mark.asyncio
async def test_runtime_enforces_tool_step_limit() -> None:
    engine, _ = runtime((AssistantTurn(tool_calls=(echo_call("one"),)),), max_steps=1)

    with pytest.raises(AssistantToolStepLimitError):
        await engine.run(
            agent=RuntimeAgent(response_to_tool=None),
            turn_context=turn_context(),
            user_text="hello",
            external_message_id="message",
        )


@pytest.mark.asyncio
async def test_tool_observation_remains_valid_json_when_compacted() -> None:
    engine, llm = runtime(
        (AssistantTurn(tool_calls=(echo_call("one"),)), AssistantTurn(content="done")),
        max_steps=2,
    )
    agent = RuntimeAgent(response_to_tool=None)
    engine._tool_executor = ToolExecutor(engine._tool_registry, max_result_chars=40)

    await engine.run(
        agent=agent,
        turn_context=turn_context(),
        user_text="hello",
        external_message_id="message",
    )

    observation = llm.calls[1][-1].content or ""
    assert len(observation) <= 40
    assert json.loads(observation)


@pytest.mark.asyncio
async def test_runtime_executes_only_first_mutating_call_in_a_turn() -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(MutateTool("mutate_a", calls))
    registry.register(MutateTool("mutate_b", calls))
    llm = FakeLlmClient(
        turns=(
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(id="a", name="mutate_a", arguments_json='{"value":"a"}'),
                    AssistantToolCall(id="b", name="mutate_b", arguments_json='{"value":"b"}'),
                )
            ),
            AssistantTurn(content="done"),
        )
    )
    engine = AssistantRuntime(
        llm_client=llm,
        tool_registry=registry,
        tool_executor=ToolExecutor(registry, max_result_chars=1000),
        tool_policy=StubToolPolicy(),
        max_tool_steps=3,
    )

    response = await engine.run(
        agent=RuntimeAgent(response_to_tool=None, tool_names=frozenset({"mutate_a", "mutate_b"})),
        turn_context=turn_context(),
        user_text="write",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="done")
    assert calls == ["a"]
    assert [message.tool_call_id for message in llm.calls[1] if message.role == "tool"] == [
        "a",
        "b",
    ]
    assert json.loads(llm.calls[1][-1].content or "{}")["status"] == "MUTATION_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_runtime_allows_only_one_mutation_across_multiple_tool_steps() -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(MutateTool("mutate_a", calls))
    registry.register(MutateTool("mutate_b", calls))
    llm = FakeLlmClient(
        turns=(
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(id="a", name="mutate_a", arguments_json='{"value":"a"}'),
                )
            ),
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(id="b", name="mutate_b", arguments_json='{"value":"b"}'),
                )
            ),
            AssistantTurn(content="done"),
        )
    )
    engine = AssistantRuntime(
        llm_client=llm,
        tool_registry=registry,
        tool_executor=ToolExecutor(registry, max_result_chars=1000),
        max_tool_steps=3,
    )
    agent = RuntimeAgent(response_to_tool=None, tool_names=frozenset({"mutate_a", "mutate_b"}))

    response = await engine.run(
        agent=agent,
        turn_context=turn_context(),
        user_text="write twice",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="done")
    assert calls == ["a"]
    assert [result.status for result in agent.results] == [
        "SUCCESS",
        "MUTATION_LIMIT_EXCEEDED",
    ]


@pytest.mark.asyncio
async def test_runtime_stops_tool_execution_after_terminal_result() -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(MutateTool("mutate_a", calls))
    llm = FakeLlmClient(
        turns=(
            AssistantTurn(
                tool_calls=(
                    AssistantToolCall(id="forbidden", name="echo_tool", arguments_json="{}"),
                    AssistantToolCall(
                        id="mutation", name="mutate_a", arguments_json='{"value":"unsafe"}'
                    ),
                )
            ),
        )
    )
    engine = AssistantRuntime(
        llm_client=llm,
        tool_registry=registry,
        tool_executor=ToolExecutor(registry, max_result_chars=1000),
        max_tool_steps=2,
    )
    agent = RuntimeAgent(response_to_tool=None, tool_names=frozenset({"mutate_a"}))

    response = await engine.run(
        agent=agent,
        allowed_names=frozenset({"mutate_a"}),
        turn_context=turn_context(),
        user_text="unsafe",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="当前不可使用该工具")
    assert calls == []
    assert [result.status for result in agent.results] == ["PERMISSION_DENIED"]


@pytest.mark.asyncio
async def test_runtime_handles_unknown_tool_without_crashing() -> None:
    unknown = AssistantToolCall(
        id="unknown",
        name="totally_nonexistent_procurement_tool",
        arguments_json="{}",
    )
    engine, llm = runtime((AssistantTurn(tool_calls=(unknown,)), AssistantTurn(content="safe")))
    agent = RuntimeAgent(response_to_tool=None)

    response = await engine.run(
        agent=agent,
        turn_context=turn_context(),
        user_text="unknown",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="safe")
    assert [result.status for result in agent.results] == ["NOT_FOUND"]
    assert json.loads(llm.calls[1][-1].content or "{}")["status"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_runtime_enforces_total_tool_call_limit() -> None:
    engine, _ = runtime(
        (AssistantTurn(tool_calls=(echo_call("one"), echo_call("two"), echo_call("three"))),),
        max_total_calls=2,
    )
    agent = RuntimeAgent(response_to_tool=None)

    response = await engine.run(
        agent=agent,
        turn_context=turn_context(),
        user_text="many reads",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(
        text="本轮工具调用次数已达上限，请缩小请求范围后重试。"  # noqa: RUF001
    )
    assert [result.status for result in agent.results] == [
        "SUCCESS",
        "SUCCESS",
        "TOOL_CALL_LIMIT_EXCEEDED",
    ]


def test_tool_observation_never_exceeds_max_result_chars() -> None:
    registry = ToolRegistry()
    executor = ToolExecutor(registry, max_result_chars=64)
    nested: dict[str, object] = {"values": ["字段" * 500 for _ in range(100)]}
    for _ in range(25):
        nested = {"nested": nested}
    result = LargeResult(
        status="SUCCESS",
        user_message="消息" * 2000,
        updated_fields=nested,
        missing_fields=["缺失字段" * 100 for _ in range(100)],
    )

    observation = executor.observation(
        name="large", tool_call_id="large-call", result=result
    ).content

    assert observation is not None
    assert len(observation) <= 64
    assert isinstance(json.loads(observation), dict)


@pytest.mark.asyncio
async def test_fact_request_requires_tool_grounding_before_final_answer() -> None:
    calls: list[str] = []
    tool_name = "get_purchase_request"
    engine, llm = grounded_runtime(
        (
            AssistantTurn(content="PR-123 is completed."),
            AssistantTurn(tool_calls=(read_call("fact", tool_name),)),
            AssistantTurn(content="The backend reports that PR-123 is completed."),
        ),
        ReadTool(tool_name, calls),
    )
    agent = RuntimeAgent(response_to_tool=None, tool_names=frozenset({tool_name}))

    response = await engine.run(
        agent=agent,
        grounding=GroundingDecision(GroundingRequirement.BACKEND_FACT, frozenset({tool_name})),
        turn_context=turn_context(),
        user_text="What is the status of purchase request PR-123?",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="The backend reports that PR-123 is completed.")
    assert calls == ["evidence"]
    assert "必须先调用" in (llm.calls[1][-1].content or "")


@pytest.mark.asyncio
async def test_supplier_recommendation_requires_recommendation_tool() -> None:
    calls: list[str] = []
    tool_name = "recommend_suppliers"
    engine, _ = grounded_runtime(
        (
            AssistantTurn(content="Supplier A, Supplier B, Supplier C."),
            AssistantTurn(tool_calls=(read_call("supplier", tool_name),)),
            AssistantTurn(content="Based on the returned candidates, consider Supplier A."),
        ),
        ReadTool(tool_name, calls),
    )

    response = await engine.run(
        agent=RuntimeAgent(response_to_tool=None, tool_names=frozenset({tool_name})),
        grounding=GroundingDecision(
            GroundingRequirement.SUPPLIER_RECOMMENDATION, frozenset({tool_name})
        ),
        turn_context=turn_context(),
        user_text="Recommend three suppliers.",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(
        text="Based on the returned candidates, consider Supplier A."
    )
    assert calls == ["evidence"]


@pytest.mark.asyncio
async def test_product_recommendation_requires_product_tool() -> None:
    calls: list[str] = []
    tool_name = "recommend_products"
    engine, _ = grounded_runtime(
        (
            AssistantTurn(content="Use model X."),
            AssistantTurn(tool_calls=(read_call("product", tool_name),)),
            AssistantTurn(content="Model X appears in the backend candidates."),
        ),
        ReadTool(tool_name, calls),
    )

    response = await engine.run(
        agent=RuntimeAgent(response_to_tool=None, tool_names=frozenset({tool_name})),
        grounding=GroundingDecision(
            GroundingRequirement.PRODUCT_RECOMMENDATION, frozenset({tool_name})
        ),
        turn_context=turn_context(),
        user_text="Recommend suitable switches.",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="Model X appears in the backend candidates.")
    assert calls == ["evidence"]


@pytest.mark.asyncio
async def test_unrelated_tool_does_not_satisfy_grounding_requirement() -> None:
    calls: list[str] = []
    tool_name = "recommend_suppliers"
    engine, llm = grounded_runtime(
        (
            AssistantTurn(tool_calls=(echo_call("unrelated"),)),
            AssistantTurn(content="Fabricated supplier."),
            AssistantTurn(tool_calls=(read_call("supplier", tool_name),)),
            AssistantTurn(content="Grounded supplier."),
        ),
        ReadTool(tool_name, calls),
    )

    response = await engine.run(
        agent=RuntimeAgent(
            response_to_tool=None,
            tool_names=frozenset({"echo_tool", tool_name}),
        ),
        grounding=GroundingDecision(
            GroundingRequirement.SUPPLIER_RECOMMENDATION, frozenset({tool_name})
        ),
        turn_context=turn_context(),
        user_text="Recommend suppliers.",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="Grounded supplier.")
    assert calls == ["evidence"]
    assert "必须先调用" in (llm.calls[2][-1].content or "")


@pytest.mark.asyncio
async def test_relevant_tool_allows_grounded_final_answer() -> None:
    calls: list[str] = []
    tool_name = "compare_suppliers"
    engine, _ = grounded_runtime(
        (
            AssistantTurn(tool_calls=(read_call("comparison", tool_name),)),
            AssistantTurn(content="Supplier A has the stronger documented fit."),
        ),
        ReadTool(tool_name, calls),
    )

    response = await engine.run(
        agent=RuntimeAgent(response_to_tool=None, tool_names=frozenset({tool_name})),
        grounding=GroundingDecision(
            GroundingRequirement.SUPPLIER_COMPARISON, frozenset({tool_name})
        ),
        turn_context=turn_context(),
        user_text="Compare these suppliers.",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="Supplier A has the stronger documented fit.")
    assert calls == ["evidence"]


@pytest.mark.asyncio
async def test_general_explanation_does_not_require_grounding_tool() -> None:
    policy = GroundingPolicy()
    decision = policy.decide(
        "What factors should I consider when choosing a supplier?",
        available_tools=frozenset({"recommend_suppliers"}),
    )
    engine, _ = grounded_runtime((AssistantTurn(content="Consider quality and delivery."),))

    response = await engine.run(
        agent=RuntimeAgent(response_to_tool=None),
        grounding=decision,
        turn_context=turn_context(),
        user_text="What factors should I consider when choosing a supplier?",
        external_message_id="message",
    )

    assert decision.requirement is GroundingRequirement.NONE
    assert response == AssistantTextResponse(text="Consider quality and delivery.")


@pytest.mark.asyncio
async def test_grounding_tool_failure_does_not_retry_indefinitely() -> None:
    calls: list[str] = []
    tool_name = "get_purchase_request"
    engine, llm = grounded_runtime(
        (AssistantTurn(tool_calls=(read_call("failed", tool_name),)),),
        ReadTool(tool_name, calls, status="BACKEND_UNAVAILABLE"),
    )

    response = await engine.run(
        agent=RuntimeAgent(response_to_tool=None, tool_names=frozenset({tool_name})),
        grounding=GroundingDecision(GroundingRequirement.BACKEND_FACT, frozenset({tool_name})),
        turn_context=turn_context(),
        user_text="What is the status of purchase request PR-123?",
        external_message_id="message",
    )

    assert response == AssistantTextResponse(text="evidence")
    assert calls == ["evidence"]
    assert len(llm.calls) == 1


@pytest.mark.parametrize(
    ("text", "expected", "relevant_tool"),
    (
        (
            "What is the status of purchase request PR-123?",
            GroundingRequirement.BACKEND_FACT,
            "get_purchase_request",
        ),
        (
            "Recommend three suppliers for these laptops.",
            GroundingRequirement.SUPPLIER_RECOMMENDATION,
            "recommend_suppliers",
        ),
        (
            "Recommend suitable switches for this request.",
            GroundingRequirement.PRODUCT_RECOMMENDATION,
            "recommend_products",
        ),
        (
            "Compare these suppliers.",
            GroundingRequirement.SUPPLIER_COMPARISON,
            "compare_suppliers",
        ),
        (
            "Compare these product candidates.",
            GroundingRequirement.PRODUCT_COMPARISON,
            "compare_products",
        ),
        (
            "Which supplier did we use last time?",
            GroundingRequirement.PURCHASE_HISTORY,
            "find_similar_purchases",
        ),
    ),
)
def test_grounding_policy_classifies_authoritative_requests(
    text: str, expected: GroundingRequirement, relevant_tool: str
) -> None:
    decision = GroundingPolicy().decide(
        text,
        available_tools=frozenset(
            {
                "get_purchase_request",
                "recommend_suppliers",
                "recommend_products",
                "compare_suppliers",
                "compare_products",
                "find_similar_purchases",
            }
        ),
    )

    assert decision.requirement is expected
    assert relevant_tool in decision.relevant_tool_names
