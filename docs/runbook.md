# Production Runbook

## Dependencies and startup

Production requires the procurement backend, Redis, Feishu credentials, and (only when the
optional text assistant is enabled) an OpenAI-compatible model endpoint. Run one or more workers
only with all three persistence selectors set to `redis`:

```text
PROCUREMENT_EVENT_DEDUP_STORE_BACKEND=redis
PROCUREMENT_CONVERSATION_LOCK_BACKEND=redis
PROCUREMENT_NOTIFICATION_DELIVERY_STORE_BACKEND=redis
PROCUREMENT_REDIS_URL=redis://...
```

Redis URL is treated as a secret and must not be logged. Configure the event dedup, lock lease,
lock acquisition, delivery TTL, Redis timeout, backend timeout and LLM timeout with the settings
documented in `README.md`. Production startup fails closed for memory dedup, local conversation
locks, memory notification delivery, fake backend, debug identity probe, or missing Redis URL.

Start the ASGI service with the deployment platform's normal Uvicorn/Gunicorn command. Keep
`PROCUREMENT_LLM_ENABLED=false` unless the optional assistant has passed deterministic evals and
the release-gated live-model eval.

## Health and incidents

- `/health/live` checks the process only and never calls the LLM.
- `/health/ready` reports configured backend and persistence modes.
- A backend or session failure must surface as an error; it is never converted to an empty result.
- Redis failure is fail-closed for event dedup, conversation serialization, and notification
  idempotency. Do not silently switch a multi-worker deployment to memory stores.
- Conversation lock timeout is safe to retry as a new inbound delivery after the current lease
  holder finishes. Owner-checked release prevents one worker from deleting another worker's lock.
- Backend mutations are not blindly retried. Formal actions retain `expected_version` and stable
  `action_token`; concurrent modification causes a fresh detail read in the deterministic card path.
- LLM timeout/provider failure ends the optional assistant turn safely. Formal state transitions
  remain card-only and are never replayed by the Agent.

## Verification

```text
ruff format --check .
ruff check .
mypy src tests
pytest -q tests/unit
pytest -q tests/integration
pytest -q tests/contract
pytest -q tests/evals -m "not live_llm"
```

Live model eval is manual/nightly/release-only because it is slow, costly, and nondeterministic.
