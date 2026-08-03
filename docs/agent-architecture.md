# Task 8 Agent architecture

`ProcurementAssistant` is an optional text-message path. Formal Feishu cards remain deterministic and never invoke an LLM.

Text messages are deduplicated by the existing webhook store, then serialized by `LocalConversationLockManager` using `FEISHU:<platform_user_id>`. The lock covers current-user lookup, backend session access, LLM calls, tool execution, state work, and reply dispatch. Different users have distinct locks and run concurrently. This lock is process-local; a multi-worker deployment must replace it with a backend-provided conversation lease or distributed lock.

The assistant depends on the `LlmClient` port. `OpenAICompatibleLlmClient` is the production adapter; `FakeLlmClient` and `EchoTool` are test-only building blocks. `ToolRegistry` generates schemas from Pydantic, while `ToolExecutor` parses strict JSON-object arguments and returns platform-neutral tool messages. Production policy currently exposes no business tools.

Conversation messages and short-lived state use the procurement backend's Agent REST endpoints through `BackendClient`. Backend data remains authoritative. The assistant may explain or recommend but cannot perform formal workflow transitions; those must use cards with backend-issued facts, versions, and action tokens.

Enable it with `PROCUREMENT_LLM_ENABLED=true` plus a model and API key. When disabled, the card workflow is unchanged and ordinary text receives a disabled response. Task 9 can add read-only procurement tools through the existing registry and policy.
