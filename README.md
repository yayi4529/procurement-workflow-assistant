# Procurement Workflow Assistant

飞书采购流程助手的单仓库工程，包含：

- `src/`：飞书 Webhook、正式卡片流程、可选文本 Agent 和 HTTP Backend Adapter。
- `backend/`：采购业务 FastAPI 后端、MySQL/Redis、Agent Session 和通知 Outbox。
- `tests/`：Agent、卡片、集成、契约和安全回归测试。

正式采购动作始终由确定性的飞书卡片完成。文本 Agent 只负责查询、解释、推荐和草稿辅助，
不会直接提交、驳回、开始采购或确认完成。

## Runtime topology

```text
Feishu → Agent service :8000 → HMAC HTTP → Procurement backend :8001
                                               ├─ MySQL :3307
                                               └─ Redis :6380
```

| Service | URL |
|---|---|
| Agent liveness | `http://127.0.0.1:8000/health/live` |
| Agent readiness | `http://127.0.0.1:8000/health/ready` |
| Feishu webhook | `http://127.0.0.1:8000/webhooks/feishu` |
| Backend health | `http://127.0.0.1:8001/health` |
| Backend readiness | `http://127.0.0.1:8001/ready` |
| Backend OpenAPI | `http://127.0.0.1:8001/openapi.json` |

## Architecture

```text
AssistantService → ContextBuilder → CapabilityPolicy → ProcurementAgent
→ AssistantRuntime → CapabilityRegistry → Domain Capability → BackendClient HTTP Port
```

正式动作使用独立链路：

```text
Feishu Card → Action Router → Application Service → Backend
```

`BusinessFacts` 从后端事实重建；`AgentTaskState` 和 `ReferenceStore` 通过后端 Agent Session
跨 worker 持久化。角色只决定能力权限并集，不再切换 RoleAgent。

当前文本能力包括采购需求诊断、历史采购查询、产品/供应商比较、供应商资料查询、推荐、
状态和时间线查询，以及各角色草稿字段辅助。所有 LLM-visible Capability 都不执行正式
状态流转，并且每轮最多执行一个 MUTATE 草稿操作。

## Requirements

- Python 3.11+（后端推荐 Python 3.12）
- Docker Desktop
- MySQL 8 和 Redis 7（由 `backend/compose.yaml` 提供）
- 可选：真实飞书应用、OpenAI-compatible LLM endpoint、Cloudflare Tunnel

## Quick start

### Start backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts\bootstrap_env.py
docker compose --env-file .env.docker up -d
python -m alembic upgrade head
\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
```

### Start Agent

Copy `.env.example` or an existing local environment file to `.env`, then configure the backend URL,
HMAC secret and optional LLM credentials.

```powershell
cd ..
.\scripts\start_http_integration.ps1 `
  -EnvFile .env `
  -BackendBaseUrl http://127.0.0.1:8001 `
  -HostAddress 0.0.0.0 `
  -Port 8000 `
  -EnableLlm
```

For Feishu + Fake Backend development:

```powershell
.\scripts\start_feishu_fake.ps1 -EnvFile .env.feishu-fake -HostAddress 0.0.0.0 -Port 8000
```

Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8001/ready
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

## Feishu public webhook

For temporary development exposure:

```powershell
.\scripts\start_feishu_tunnel.ps1 -Provider cloudflared -LocalUrl http://127.0.0.1:8000
```

In the Feishu developer console, use the generated HTTPS URL plus `/webhooks/feishu`:

```text
https://YOUR-QUICK-TUNNEL.trycloudflare.com/webhooks/feishu
```

Quick Tunnels are temporary; use a named tunnel for long-running environments.

## Production safety

Production must use distributed Redis persistence:

```dotenv
PROCUREMENT_EVENT_DEDUP_STORE_BACKEND=redis
PROCUREMENT_CONVERSATION_LOCK_BACKEND=redis
PROCUREMENT_NOTIFICATION_DELIVERY_STORE_BACKEND=redis
PROCUREMENT_REDIS_URL=redis://user:password@host:6379/0
```

Production rejects memory deduplication, local conversation locks, Fake Backend, missing Redis URL,
and development identity probing. See [docs/runbook.md](docs/runbook.md).

Never commit Feishu secrets, `IDENTITY_GATEWAY_SECRET`, LLM keys, Redis passwords, notification
tokens, `.env`, `.env.docker`, `.venv`, logs or generated outputs.

## Testing and CI

```powershell
ruff format --check .
ruff check .
mypy src
pytest -q
git diff --check
```

GitHub Actions runs format, lint, source type checks, unit, integration, contract and deterministic
Agent evals. Live-model evals are manual/release-only. See [docs/eval-baseline.md](docs/eval-baseline.md).

## Documentation

- [Data Center Asset Domain](docs/data-center-asset-domain.md)
- [Task06 Multi-item Workflow](docs/task06-multi-item-workflow.md)
- [Production Runbook](docs/runbook.md)
- [Architecture](docs/architecture.md)
- [Agent Architecture](docs/agent-architecture.md)
- [Backend Contract](docs/backend-contract.md)
- [Testing Strategy](docs/testing-strategy.md)
- [No-LLM E2E Acceptance](docs/no-llm-e2e-acceptance.md)
- [Feishu Fake Debugging](docs/feishu-fake-debugging.md)
- [Backend README](backend/README.md)

The backend remains independently runnable from `backend/`, while this GitHub repository is the
single integrated project.
