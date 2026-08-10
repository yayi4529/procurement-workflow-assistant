# Task 8 Agent architecture

`AssistantService` is the optional text-message entry. `ProcurementAssistant` remains only as a thin compatibility wrapper. Formal Feishu cards remain deterministic and never invoke an LLM.

```text
BaseMessageHandler
→ AssistantService
→ AgentRouter
→ ApplicantAgent / BuildingManagerAgent / PurchaserAgent / WarehouseAgent
→ AssistantRuntime
→ LlmClient + ToolExecutor
```

`AssistantService` owns identity, session, deduplication, history and routing. `AssistantRuntime` owns the shared LLM tool-calling loop and does not import role-specific results or card factories. Each `RoleAgent` owns its prompt, tool set and deterministic handling of role-specific tool results.

Text messages are deduplicated by the existing webhook store, then serialized by `LocalConversationLockManager` using `FEISHU:<platform_user_id>`. The lock covers current-user lookup, backend session access, LLM calls, tool execution, state work, and reply dispatch. Different users have distinct locks and run concurrently. This lock is process-local; a multi-worker deployment must replace it with a backend-provided conversation lease or distributed lock.

The assistant depends on the `LlmClient` port. `OpenAICompatibleLlmClient` is the production adapter; `FakeLlmClient` and `EchoTool` are test-only building blocks. `ToolRegistry` generates schemas from strict Pydantic argument models, while `ToolExecutor` returns structured results. Exact supplier fields and purchase prefill results bypass LLM rewriting. Candidate references and active requirement context are stored in the backend Agent session.

Task 9 registers nine tools with an exact role matrix. `ToolPolicy` receives one active role and never merges all roles held by a user. `AgentRouter` reuses `AgentSessionState.focused_role`; a multi-role user without a valid focus must choose a role explicitly. Every execution re-fetches the current user and authoritative requirement detail through `BackendClient`. Draft tools require the correct handler/status and latest `version`; they never submit, reject, start purchase, submit to warehouse, or complete a requirement. The detailed contract is documented in `docs/agent-tools.md`.

For `REQUIREMENT_PENDING_PURCHASE`, the notification gateway may ask an isolated prefill provider to render a purchaser suggestion card. Any unavailable, invalid, unauthorized, or incomplete prefill falls back to the ordinary Outbox notification. The gateway itself has no dependency on business transition operations.

Conversation messages and short-lived state use the procurement backend's Agent REST endpoints through `BackendClient`. Backend data remains authoritative. The assistant may explain or recommend but cannot perform formal workflow transitions; those must use cards with backend-issued facts, versions, and action tokens.

Enable it with `PROCUREMENT_LLM_ENABLED=true` plus a model and API key. When disabled, the card workflow is unchanged and ordinary text receives a disabled response.
