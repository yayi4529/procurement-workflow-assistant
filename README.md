# Procurement Workflow Assistant

基于飞书卡片、平台无关通知网关和可选智能助手的采购流程自动化前端服务。

当前项目已完成 Task 1～Task 7 的无 LLM 正式采购流程，现进入：

> **真实飞书 + 真实采购后端联调阶段**

Task 8～Task 9 已完成可选、默认关闭的文本 Assistant 基础设施和九个角色工具。详见 [Agent 架构](docs/agent-architecture.md) 与 [Agent 工具](docs/agent-tools.md)；正式采购卡片不依赖，也不会进入 LLM。

启用文本 Assistant 需要显式设置 `PROCUREMENT_LLM_ENABLED=true`，并提供
`PROCUREMENT_LLM_API_KEY` 与 `PROCUREMENT_LLM_MODEL`（可选 `PROCUREMENT_LLM_BASE_URL`）。
启用后，文本消息由 `AssistantService → AgentRouter → RoleAgent → AssistantRuntime`
处理，`ToolPolicy` 只开放当前激活角色的 Task 9 工具；多角色用户需先选择工作角色。
草稿工具只保存字段，提交、驳回、开始采购和确认完成仍只能使用正式卡片，并继续走后端签名、版本号与 action token 流程。

正式业务事实、身份、角色、楼宇、状态、处理人、版本、幂等和审计全部以后端为准。本项目负责飞书消息与卡片交互、后端 HTTP 适配、通知网关和后续智能助手能力。

---

## 1. 当前联调拓扑

```text
真实飞书用户
    ↓
飞书 Webhook / 卡片回调
    ↓
procurement-workflow-assistant
    ├── FeishuWebhookParser
    ├── CardActionRouter
    ├── Application Service
    └── HttpBackendClient
            ↓ HMAC 身份签名
采购后端 http://127.0.0.1:8001
    ├── FastAPI
    ├── MySQL 127.0.0.1:3307
    ├── Redis 127.0.0.1:6380
    └── notification_outbox
            ↓
本项目通知网关 http://127.0.0.1:8000/internal/notifications
            ↓
真实飞书主动消息
```

当前建议端口：

| 组件 | 地址 |
|---|---|
| 本项目 | `http://127.0.0.1:8000` |
| 采购后端 | `http://127.0.0.1:8001` |
| 后端 MySQL | `127.0.0.1:3307` |
| 后端 Redis | `127.0.0.1:6380` |
| 本项目 Health | `http://127.0.0.1:8000/health/live` |
| 本项目 Readiness | `http://127.0.0.1:8000/health/ready` |
| 后端 Health | `http://127.0.0.1:8001/health` |
| 后端 Readiness | `http://127.0.0.1:8001/ready` |
| 后端 Swagger | `http://127.0.0.1:8001/docs` |
| 后端 OpenAPI | `http://127.0.0.1:8001/openapi.json` |
| 后端 Demo | `http://127.0.0.1:8001/demo/` |

---

## 2. 核心原则

### 2.1 正式流程不依赖 LLM

以下操作完全不依赖 LLM：

```text
需求人创建和提交
楼长保存、驳回和提交采购员
采购员开始采购、保存和提交仓库
仓库保存和确认完成
```

即使没有 OpenAI 配置，采购流程也必须可以运行。

### 2.2 后端是唯一事实来源

以下内容只采用后端响应：

```text
当前员工
角色
楼宇
采购字段
missing_fields
allowed_actions
status
current_handler
version
处理人候选
供应商和黑名单
统计数字
```

本项目不得直接访问采购后端 MySQL 或 Redis。

### 2.3 并发和幂等

```text
字段保存：expected_version
正式动作：action_token
Webhook 去重：event/message identifier
通知投递：Idempotency-Key
```

遇到版本冲突时重新获取详情，禁止自动覆盖。

### 2.4 通知只走 Outbox

```text
后端业务事务
→ notification_outbox
→ 后端 Worker
→ 本项目通知网关
→ 飞书
```

业务接口成功后，本项目不得再次直接发送同一跨角色通知。

---

## 3. 已完成能力

### Task 1：后端适配基础

- 强类型 Settings；
- `GatewayIdentitySigner`；
- `SignedBackendTransport`；
- `BackendClient` Protocol；
- `HttpBackendClient`；
- `FakeBackendClient`；
- 统一后端 Envelope 和错误映射；
- `/health/live`、`/health/ready`；
- 当前用户和 Agent 会话接口基础适配。

### Task 2：飞书与通知基础

- 飞书 Challenge、验签、解密；
- 私聊文本和卡片回调解析；
- 平台无关 `InteractionView`；
- 飞书卡片渲染；
- 回复、更新、主动发送；
- 事件去重；
- 通知网关；
- 通知投递幂等；
- 开发通知 Smoke。

### Task 3～6：四角色正式卡片流程

```text
APPLICANT
BUILDING_MANAGER
PURCHASER
WAREHOUSE_MANAGER
```

支持状态链：

```text
DRAFT
→ PENDING_REVIEW
→ REJECTED
→ PENDING_REVIEW
→ PENDING_PURCHASE
→ PURCHASING
→ PENDING_WAREHOUSE
→ COMPLETED
```

### Task 7：无 LLM E2E

已使用同一个 `FakeBackendClient` 验证正常路径、驳回重提、权限、版本冲突和重复动作。

这不等于真实后端契约已经完全对齐。真实联调必须以运行中的 `/openapi.json` 和实际响应为准。

---

## 4. 仓库放置

两个仓库应并列，不要嵌套：

```text
D:\
├── procurement-workflow-assistant
└── procurement-agent-backend
```

---

## 5. 前置条件

### 本项目

```text
Python 3.11+
```

安装：

```powershell
cd D:\procurement-workflow-assistant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### 采购后端

```text
Python 3.12.x
Docker Desktop
MySQL 容器
Redis 容器
Alembic 迁移完成
后端运行在 127.0.0.1:8001
```

先验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8001/ready
```

---

## 6. 保存真实后端 OpenAPI

```powershell
cd D:\procurement-workflow-assistant
New-Item -ItemType Directory -Force .local

Invoke-WebRequest `
  http://127.0.0.1:8001/openapi.json `
  -OutFile .local\backend-openapi-8001.json
```

`.local/` 不得提交 Git。后端更新后重新保存并检查契约差异。

---

## 7. 创建真实后端联调配置

创建本地文件：

```text
.env.backend-integration
```

示例：

```dotenv
PROCUREMENT_ENVIRONMENT=development
PROCUREMENT_SERVICE_NAME=procurement-workflow-assistant

PROCUREMENT_BACKEND_MODE=http
PROCUREMENT_BACKEND_BASE_URL=http://127.0.0.1:8001
PROCUREMENT_BACKEND_REQUEST_TIMEOUT_SECONDS=10

# 必须与后端本地 IDENTITY_GATEWAY_SECRET 完全一致
PROCUREMENT_IDENTITY_GATEWAY_SECRET=
PROCUREMENT_ALLOW_TEST_PLATFORM=false

PROCUREMENT_FEISHU_ENABLED=true
PROCUREMENT_FEISHU_APP_ID=
PROCUREMENT_FEISHU_APP_SECRET=
PROCUREMENT_FEISHU_VERIFICATION_TOKEN=
PROCUREMENT_FEISHU_ENCRYPT_KEY=
PROCUREMENT_FEISHU_WEBHOOK_PATH=/webhooks/feishu

# 第一阶段先关闭正式通知联调
PROCUREMENT_NOTIFICATION_GATEWAY_ENABLED=false
PROCUREMENT_NOTIFICATION_GATEWAY_PATH=/internal/notifications
PROCUREMENT_NOTIFICATION_GATEWAY_TOKEN=
PROCUREMENT_NOTIFICATION_DELIVERY_STORE_BACKEND=memory

PROCUREMENT_EVENT_DEDUP_STORE_BACKEND=memory
PROCUREMENT_LLM_ENABLED=false

PROCUREMENT_DEBUG_IDENTITY_PROBE_ENABLED=true
PROCUREMENT_DEVELOPMENT_NOTIFICATION_RENDERER_ENABLED=false

PROCUREMENT_LOG_LEVEL=INFO
PROCUREMENT_LOG_FORMAT=json
```

不得提交或记录：

```text
飞书 App Secret
Verification Token
Encrypt Key
IDENTITY_GATEWAY_SECRET
Notification Token
```

---

## 8. HMAC 身份签名

所有 `/api/v1/*` 后端请求必须携带：

```text
X-Platform-Type
X-Platform-User-Id
X-Gateway-Timestamp
X-Gateway-Nonce
X-Gateway-Signature
```

签名原文：

```text
HTTP_METHOD
URL_PATH
PLATFORM_TYPE
PLATFORM_USER_ID
TIMESTAMP
NONCE
```

要求：

- HTTP Method 使用大写；
- 只签 path，不签 query string；
- `PLATFORM_TYPE` 使用大写；
- 每次重试重新生成 timestamp、nonce 和 signature；
- 两端 `IDENTITY_GATEWAY_SECRET` 必须一致。

---

## 9. 真实飞书身份映射

后端根据：

```text
FEISHU + open_id
```

解析员工、角色和楼宇。本项目不能自行声明 `employee_id`、角色、楼宇或当前处理人。

### 获取 open_id

四个测试账号分别私聊机器人：

```text
调试身份
```

记录回复中的：

```text
platform_user_id: ou_xxxxx
```

### 后端测试员工建议

| 测试角色 | 后端员工 |
|---|---:|
| 需求人 | `90001` |
| 一号楼楼长 | `90002` |
| 采购员 | `90003` |
| 仓库管理员 | `90004` |

由后端种子脚本、联调脚本或后端管理员完成 `FEISHU open_id` 映射。本项目不得增加直连 MySQL 的身份绑定实现。

绑定后首先验证：

```http
GET /api/v1/users/me
```

---

## 10. 启动本项目

```powershell
cd D:\procurement-workflow-assistant
.\.venv\Scripts\Activate.ps1

python -m uvicorn `
  --factory procurement_platform.interfaces.http.app:create_app `
  --env-file .env.backend-integration `
  --host 0.0.0.0 `
  --port 8000 `
  --workers 1
```

检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

Readiness 应至少表明：

```text
backend_mode=http
backend_configured=true
feishu_configured=true
llm_enabled=false
```

开发阶段使用内存去重 Store 时保持单 worker。

---

## 11. 当前真实契约对齐重点

现有 Fake/文档模型与真实后端响应存在已知差异，不能通过 `extra="ignore"` 粗暴绕过。

### 当前用户

后端真实数据包含：

```text
employee_id
employee_no
name
mobile
status
platform_type
platform_user_id
roles[].role_id
roles[].role_code
roles[].role_name
buildings[]
```

正确处理：

```text
BackendCurrentUserDTO
→ 显式 Mapper
→ CurrentUser Domain
```

### 采购列表

后端列表项主要返回：

```text
requirement_id
requirement_no
device_name
status
current_handler_name
```

不要假设列表项必返 `version` 或完整处理人。需要操作时重新调用详情接口。

### 采购详情

后端详情使用：

```text
review_records
purchase_execution
warehouse_receipt
```

项目领域层使用的展示模型可能不同，应在 Adapter 中显式映射。

### 字段保存响应

后端字段保存主要返回：

```text
requirement_id
status
version
missing_fields
next_missing_field
fields_complete
```

如果卡片需要完整字段：

```text
PATCH 保存
→ 解析最小保存结果
→ GET 最新详情
→ 渲染卡片
```

不要假设 PATCH 响应包含完整嵌套快照。

---

## 12. 推荐联调顺序

### 阶段 1：基础连接

```text
[ ] 后端 /health
[ ] 后端 /ready
[ ] 保存 /openapi.json
[ ] HMAC Secret 同步
[ ] backend_mode=http
[ ] 本项目 readiness 正常
```

### 阶段 2：身份

```text
[ ] 获取四个飞书 open_id
[ ] 后端完成 FEISHU 身份绑定
[ ] GET /api/v1/users/me 成功
[ ] 当前用户 DTO 映射成功
```

### 阶段 3：需求人

```text
[ ] 创建 DRAFT
[ ] 保存 applicant-fields
[ ] 获取详情
[ ] 获取楼长候选
[ ] submit-review
```

### 阶段 4：楼长

```text
[ ] PENDING_FOR_ME
[ ] 获取详情
[ ] 保存 review-fields
[ ] reject
[ ] resubmit-review
[ ] submit-purchaser
```

### 阶段 5：采购员

```text
[ ] start-purchase
[ ] 查询/选择供应商
[ ] 保存 purchase-fields
[ ] submit-warehouse
```

### 阶段 6：仓库管理员

```text
[ ] 保存 warehouse-fields
[ ] complete
[ ] COMPLETED
[ ] current_handler 为空
```

### 阶段 7：异常

```text
[ ] 旧 expected_version
[ ] 重复 action_token
[ ] 非当前处理人
[ ] 楼长跨楼宇
[ ] 非法候选人
[ ] 后端 timeout
[ ] 非 JSON 响应
```

### 阶段 8：通知

业务状态链全部通过后再启用：

```text
notification_outbox
→ Worker
→ Notification Gateway
→ Feishu
```

在正式 `event_type` 和 Payload 未冻结前，不创造生产 Renderer。

---

## 13. 测试命令

```powershell
ruff format .
ruff format --check .
ruff check .
mypy src
pytest -q
git diff --check
git status --short
```

真实后端 Smoke 使用隔离 TEST 数据，并记录：

```text
接口
HTTP 状态
业务 code
trace_id
requirement_id
old/new version
old/new status
current_handler
```

不得记录 Secret 或完整银行账号。

---

## 14. 常见错误

### `BACKEND_UNAVAILABLE`

检查后端 8001、`PROCUREMENT_BACKEND_BASE_URL` 和 timeout。

### 签名错误

检查两端 Secret、系统时间、签名 path、platform type 和 nonce。

### `USER_NOT_FOUND`

表示 `FEISHU + open_id` 尚未映射到后端员工。

### `BACKEND_INVALID_DATA`

通常表示接口已经通了，但 DTO 与真实响应不一致。应修改 Backend DTO 和 Mapper，不能放宽全部模型。

### `CONCURRENT_MODIFICATION`

重新获取详情和最新 version，不自动覆盖。

### `DUPLICATE_OPERATION`

使用同一 action_token 查询当前状态；已达到目标状态时按幂等结果展示。

### 飞书可收消息但无法进入业务卡片

检查 HTTP Backend 模式下，确定性命令入口是否注入了真实 `backend_client`。

---

## 15. 通知联调

第一轮业务联调建议关闭通知网关。

业务状态稳定后，后端配置：

```dotenv
NOTIFICATION_GATEWAY_URL=http://127.0.0.1:8000/internal/notifications
NOTIFICATION_GATEWAY_TOKEN=
```

本项目配置：

```dotenv
PROCUREMENT_NOTIFICATION_GATEWAY_ENABLED=true
PROCUREMENT_NOTIFICATION_GATEWAY_PATH=/internal/notifications
PROCUREMENT_NOTIFICATION_GATEWAY_TOKEN=
PROCUREMENT_NOTIFICATION_DELIVERY_STORE_BACKEND=memory
```

两边 Token 必须一致。

启动后端单次通知 Worker：

```powershell
python -m app.workers.notifications
```

通知失败不得回滚或重新执行业务状态转换。

---

## 16. 文档入口

开发前优先阅读：

1. `AGENTS.md`
2. `CODEX_PROJECT_SPEC.md`
3. `docs/architecture.md`
4. `docs/backend-contract.md`
5. `docs/backend-v1.5-delta.md`
6. `docs/testing-strategy.md`
7. `docs/open-decisions.md`
8. `docs/no-llm-e2e-acceptance.md`
9. `docs/feishu-fake-debugging.md`
10. 后端仓库 `docs/后端接口联调说明.md`
11. 后端运行时 `/openapi.json`

---

## 17. 当前里程碑

```text
Task 7
→ Fake Backend 无 LLM E2E 已封板

当前阶段
→ HttpBackendClient 与真实后端 8001 契约对齐
→ 四个真实飞书身份映射
→ 四角色真实业务写入联调

当前阶段
→ Task 9 角色工具、候选引用、精确字段输出和采购预填已实现
→ 继续执行真实四角色对话 Smoke

后续
→ Task 10～12 智能助手扩展
→ Task 13 生产化
```
