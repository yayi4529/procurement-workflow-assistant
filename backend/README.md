# Procurement Agent Backend

采购流程的唯一业务事实来源。后端负责身份、角色、楼宇、字段、状态机、版本、正式动作、
供应商、黑名单、Agent Session 和通知 Outbox；不负责 LLM 推理、Prompt、工具编排或飞书卡片渲染。

本目录是根仓库的 `backend/` 子项目，也可以独立运行。

## Local services

| Component | Address |
|---|---|
| FastAPI | `http://127.0.0.1:8001` |
| Health | `http://127.0.0.1:8001/health` |
| Readiness | `http://127.0.0.1:8001/ready` |
| OpenAPI | `http://127.0.0.1:8001/openapi.json` |
| MySQL | `127.0.0.1:3307` |
| Redis | `127.0.0.1:6380` |

## Setup

要求 Python 3.12、Docker Desktop 和 Docker Compose。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts\bootstrap_env.py
docker compose --env-file .env.docker up -d
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
```

启动后检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8001/ready
```

不要执行 `docker compose down -v`，除非明确需要删除本项目全部开发数据。

## API responsibilities

### Procurement workflow

`/api/v1/requirements` 提供创建草稿、保存字段、查询详情、审核、采购和入库完成等正式
流程接口。所有写操作都使用：

- `expected_version`：乐观并发控制；
- `action_token`：重复点击和消息重试幂等；
- 后端事务：状态、操作日志和 Outbox 一致提交。

正式状态链：

```text
DRAFT → PENDING_REVIEW → REJECTED → PENDING_REVIEW
      → PENDING_PURCHASE → PURCHASING → PENDING_WAREHOUSE → COMPLETED
```

### Identity and authorization

除 `/health`、`/ready` 和 `/openapi.json` 外，业务接口需要网关签名头：

```text
X-Platform-Type
X-Platform-User-Id
X-Gateway-Timestamp
X-Gateway-Nonce
X-Gateway-Signature
```

签名 Secret 只存在服务端环境变量。操作者身份从 `platform_type + platform_user_id` 解析，
客户端不能自行声明 employee、role 或 building。

### Suppliers and recommendations

后端提供供应商搜索、详情、黑名单、产品推荐、采购历史和供应商推荐。黑名单与权限判断
由后端完成，Agent 只能使用返回的结构化事实。

### Data center assets (Task05)

The backend owns five asset tables (`equipment_category`, `equipment_model`, `asset`,
`asset_component`, and `asset_relation`) and exposes signed read APIs for categories, models,
asset search/detail, and aggregate asset context. Demo seed data uses only explicit `TEST-` codes.
See [Data Center Asset Domain](../docs/data-center-asset-domain.md).

### Agent Session

```text
POST /api/v1/agent/conversations/active
POST/GET /api/v1/agent/conversations/{id}/messages
GET/PUT /api/v1/agent/conversations/{id}/state
POST /api/v1/agent/conversations/{id}/snapshot
POST /api/v1/agent/conversations/{id}/complete
```

短期结构化状态存 Redis，快照和完整消息存 MySQL。Agent 本身在根项目运行于 8000，使用
HTTP Port 调用本后端，不得直连本后端数据库或 Redis。

### Notification Outbox

采购事务只写 `notification_outbox`，Worker 再调用 Agent 服务的通知网关：

```text
Business transaction → notification_outbox → Worker → Agent notification gateway → Feishu
```

单次运行 Worker：

```powershell
python -m app.workers.notifications
```

业务通知失败不能回滚或重做已成功的采购动作。

## Development data

```powershell
python scripts\seed_demo_data.py
python scripts\seed_demo_data.py --clean
```

脚本只维护带 TEST 标识的数据。真实 Feishu 身份绑定由后端脚本或管理员完成，不由根项目
直接访问数据库完成。

## Contract and tests

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

根项目保存运行时契约：

```powershell
cd ..
New-Item -ItemType Directory -Force .local
Invoke-WebRequest http://127.0.0.1:8001/openapi.json -OutFile .local\backend-openapi-8001.json
```

字段级请求和响应以运行时 OpenAPI 为准。不要用旧文档、Fake 模型或任意 JSON 覆盖真实契约。

## Task06 多采购项接口

Task06-A 新增申请项整体替换、逐项评审、逐项采购和追加收货接口，并在申请详情返回完整
履约图。正式流程继续使用七种既有状态；收货累计量、是否完成等结果由后端实时派生。
数据库升级采用连续的 expand/backfill 与 constrain 两个 Alembic revision。完整规则见根项目
`docs/task06-multi-item-procurement-model.md`。

## Security

禁止提交或记录：

- `.env`、`.env.docker`、数据库密码和 Redis 密码；
- `IDENTITY_GATEWAY_SECRET`；
- 飞书 Token、Secret 和 `Authorization`；
- 完整手机号、银行账号和原始敏感 Payload。

更多联调规则见 `docs/后端接口联调说明.md` 和根项目 [Production Runbook](../docs/runbook.md)。
