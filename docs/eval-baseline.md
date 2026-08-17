# Agent Eval Baseline

Baseline date: 2026-08-15  
Prompt: `procurement-agent-v2.1`  
Code baseline: `e591aec` plus TASK_06 hardening changes

The deterministic suite contains stable case-schema, grader and safety regression tests. The
current run completed with `10 passed, 80 skipped`; skipped cases are live-model cases and require
`RUN_LLM_EVALS=1` plus model credentials and prepared backend fixtures.

| Metric | Deterministic baseline |
|---|---:|
| Grader task completion | 1.0 |
| Capability selection accuracy | 1.0 |
| Reference resolution accuracy | Not automatically aggregated yet |
| Redundant question rate | 0.0 in grader regression |
| Unsupported claim rate | Covered by intelligence/safety properties; no aggregate yet |
| Unsafe action rate | 0.0; automatically aggregated by deterministic harness |
| Average tool calls | Automatically aggregated per executed fixture; live suite unavailable |
| Average LLM turns | Automatically aggregated per executed fixture; live suite unavailable |

Missing aggregate metrics must remain explicitly unavailable; they must not be inferred from
skipped cases. A model, prompt, Capability, or Context candidate may be released only after its
prepared-fixture report is compared with this baseline and unsafe action rate remains zero.

Task04 adds `average_tool_calls`, `average_llm_turns`, and `unsafe_action_rate` to deterministic
`EvalMetrics`. The scripted multi-role fixture currently records 0 tool calls, 1 LLM turn per case,
and unsafe action rate 0. Live-model aggregate values remain unavailable until those cases run.
