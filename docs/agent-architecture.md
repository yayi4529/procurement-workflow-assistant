# Task 8 Agent architecture

`AssistantService` is the optional text-message entry. `ProcurementAssistant` remains only as a thin compatibility wrapper. Formal Feishu cards remain deterministic and never invoke an LLM.

```text
BaseMessageHandler
→ AssistantService
→ ProcurementAgent
→ CapabilityPolicy（CurrentUser.roles 并集）
→ AssistantRuntime
→ CapabilityRegistry / LlmClient / ToolExecutor
```

`AssistantService` owns identity, session, deduplication, history and context preparation. The single
`ProcurementAgent` owns the domain prompt and resolves available capabilities from all roles held by
the current user. `AssistantRuntime` owns the shared LLM tool-calling loop and does not select an
Agent by role. Deterministic completed-draft card rendering is isolated in
`LegacyToolResultPresenter` as a migration compatibility layer.

Text messages are deduplicated by the existing webhook store, then serialized by `LocalConversationLockManager` using `FEISHU:<platform_user_id>`. The lock covers current-user lookup, backend session access, LLM calls, tool execution, state work, and reply dispatch. Different users have distinct locks and run concurrently. This lock is process-local; a multi-worker deployment must replace it with a backend-provided conversation lease or distributed lock.

The assistant depends on the `LlmClient` port. `OpenAICompatibleLlmClient` is the production adapter; `FakeLlmClient` and `EchoTool` are test-only building blocks. `ToolRegistry` generates schemas from strict Pydantic argument models, while `ToolExecutor` returns structured results. Exact supplier fields and purchase prefill results bypass LLM rewriting. Candidate references and active requirement context are stored in the backend Agent session.

Task 9 registers the current LLM tool set with an exact role matrix represented by capability
metadata. `CapabilityPolicy` merges all roles held by a user. `AgentSessionState.focused_role`
remains for old-session and explicit display-default compatibility but does not filter text-Agent
capabilities. Every execution re-fetches the current user and authoritative requirement detail
through `BackendClient`. Draft tools require the correct handler/status and latest `version`; they
never submit, reject, start purchase, submit to warehouse, or complete a requirement. The detailed
contract is documented in `docs/agent-tools.md`.

## Task 01 Capability compatibility architecture

The optional Assistant now has one role-authorization source in
`CapabilityMetadata.allowed_roles`. `ExistingToolCapabilityAdapter` enriches every existing
LLM-callable tool with that metadata while preserving its name, Pydantic argument schema,
side-effect classification, and execution implementation. `CapabilityRegistry` keeps the
capabilities in registration order and owns the backing `ToolRegistry` used by the current
runtime.

`CapabilityPolicy` supports the union of all roles held by a `CurrentUser`. The production text
path now passes that union from `ProcurementAgent` to `AssistantRuntime`. Legacy `ToolPolicy`,
`AgentRouter`, `RoleIntentResolver`, and the four RoleAgent classes remain only for compatibility
tests or migration imports; the ApplicationContainer no longer constructs them. Formal workflow
actions remain absent from the capability catalog.

For `REQUIREMENT_PENDING_PURCHASE`, the notification gateway may ask an isolated prefill provider to render a purchaser suggestion card. Any unavailable, invalid, unauthorized, or incomplete prefill falls back to the ordinary Outbox notification. The gateway itself has no dependency on business transition operations.

Conversation messages and short-lived state use the procurement backend's Agent REST endpoints through `BackendClient`. Backend data remains authoritative. The assistant may explain or recommend but cannot perform formal workflow transitions; those must use cards with backend-issued facts, versions, and action tokens.

Enable it with `PROCUREMENT_LLM_ENABLED=true` plus a model and API key. The production adapter uses the OpenAI-compatible Chat Completions protocol, so Qwen via DashScope can be configured with:

```dotenv
PROCUREMENT_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
PROCUREMENT_LLM_MODEL=qwen-plus
PROCUREMENT_LLM_API_KEY=<DashScope API key>
```

When disabled, the card workflow is unchanged and ordinary text receives a disabled response. Formal procurement actions never depend on this setting.

## Feishu visible progress and streaming cards

The text Agent may use a Feishu CardKit JSON 2.0 streaming card to show an auditable
processing trace: a short plan, current step, tool purpose, redacted factual observation,
elapsed time, and final answer. These events are generated status summaries, not hidden model
Chain-of-Thought. Never emit or store private token-level reasoning, system prompts, secrets,
signatures, full tool arguments, or sensitive backend payloads.

Create one processing card and update that same card as work progresses. Close streaming mode
before enabling card interactions. If an update fails, degrade to one final card and do not retry
any procurement write operation. Streaming requires `cardkit:card:write`, CardKit JSON 2.0, and
compliance with Feishu's per-card update-rate limit. Formal workflow actions remain on existing
deterministic cards.
