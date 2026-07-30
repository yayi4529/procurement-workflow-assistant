# Procurement Workflow Assistant

基于飞书卡片、智能助手和平台无关通知网关的采购流程自动化平台。

## 核心定位

```text
正式流程：飞书卡片 → 后端
智能辅助：自然语言 → Agent → 后端查询或预填
```

即使 LLM 不可用，四角色正式流程仍必须可运行。

## 四个角色

- 需求人 `APPLICANT`
- 楼长 `BUILDING_MANAGER`
- 采购员 `PURCHASER`
- 仓库管理员 `WAREHOUSE_MANAGER`

## 数据所有权

- 飞书通讯录：身份、组织和楼宇上游来源；
- 后端：正式业务事实；
- MySQL：正式业务数据；
- Redis：Agent 实时会话；
- 本项目：飞书交互、卡片、智能助手和后端 API 适配。

## 入口

### 卡片入口

负责填写、保存、确认和状态流转，不调用 LLM。

### Agent 入口

负责查询、预填、流程说明、历史总结和卡片填写帮助。

## 文档

优先阅读：

1. `AGENTS.md`
2. `CODEX_PROJECT_SPEC.md`
3. `docs/architecture.md`
4. `docs/card-agent-interaction.md`
5. `docs/backend-contract.md`
6. `docs/assistant-session.md`
7. `docs/development-roadmap.md`
8. `docs/testing-strategy.md`
9. `docs/open-decisions.md`


## V1.5 联调关键点

- 采购后端请求使用 HMAC 身份网关签名；
- Agent 会话通过后端 HTTP 管理 Redis；
- 跨角色通知由后端 Outbox 异步调用本项目通知网关；
- 本项目不得在业务接口成功后再次主动推送同一通知；
- 契约差异见 `docs/backend-v1.5-delta.md`。

## Task 1 已实现

- `src` layout、强类型 Settings、身份/用户/Agent 会话领域模型；
- `GatewayIdentitySigner` 与 `SignedBackendTransport`；
- `BackendClient` Protocol、`HttpBackendClient`、`FakeBackendClient`；
- 统一后端 envelope 解析、错误映射、trace id 保留；
- `/health/live`、`/health/ready`；
- `/api/v1/users/me` 与全部 Agent 会话接口适配。

## Task 2 已实现

- 可配置的飞书 Webhook，支持 Challenge、Token/签名校验、加密事件解密、私聊文本和
  卡片回调解析；
- 平台无关 `InteractionView`、飞书 Renderer、回复/更新/主动发送 Channel Port；
- 并发安全的内存事件去重和通知投递幂等 Store；
- 可配置通知网关、可选 Bearer Token、Header/Body 一致性校验和 Payload 指纹；
- `NotificationRendererRegistry`，但生产容器没有注册未冻结的业务模板；
- `foundation.echo` 仅用于验证卡片回调链路，不执行采购业务。

本阶段不包含 LLM、四角色业务卡片、采购状态流转或正式业务通知 Renderer，也不直接
访问 MySQL/Redis。

## 本地开发

Python 3.11+ 环境中安装：

```bash
python -m pip install -e ".[dev]"
```

复制 `.env.example` 到本地 `.env` 或导出其中变量。必须为
`PROCUREMENT_IDENTITY_GATEWAY_SECRET` 设置开发密钥；不要提交或记录真实密钥。

运行检查：

```bash
ruff format --check .
ruff check .
mypy src
pytest -q
```

启动最小服务（`create_app` 会从环境变量加载 Settings）：

```bash
uvicorn --factory procurement_platform.interfaces.http.app:create_app
```

测试应用服务可以注入 `FakeBackendClient(CurrentUser(...))`，再构造
`ApplicationContainer(settings, fake)`；Fake 支持活动会话、消息幂等与分页、状态、
快照、完成、调用计数和按方法错误注入。

### 飞书与通知网关

```text
PROCUREMENT_FEISHU_ENABLED=true
PROCUREMENT_FEISHU_APP_ID=
PROCUREMENT_FEISHU_APP_SECRET=
PROCUREMENT_FEISHU_VERIFICATION_TOKEN=
PROCUREMENT_FEISHU_ENCRYPT_KEY=
PROCUREMENT_FEISHU_WEBHOOK_PATH=/webhooks/feishu

PROCUREMENT_NOTIFICATION_GATEWAY_ENABLED=true
PROCUREMENT_NOTIFICATION_GATEWAY_PATH=/internal/notifications
PROCUREMENT_NOTIFICATION_GATEWAY_TOKEN=
PROCUREMENT_NOTIFICATION_DELIVERY_STORE_BACKEND=memory
```

Secret 必须由部署环境注入。`/internal/notifications` 只是开发默认值，并非后端已冻结的
正式路径。配置 Token 时，Outbox worker 必须发送 Bearer Token。通知请求还必须携带与
Body 一致的 `Idempotency-Key` 和 `X-Notification-Id`。首次成功和完全相同的重复投递均
返回 `204`；后端以任意 2xx 作为成功，非 2xx 由 Outbox 重试。

`MemoryEventDedupStore` 和 `MemoryNotificationDeliveryStore` 只适合单进程开发与测试。
通知网关在 production 明确拒绝 memory Store；生产级持久化方案仍待确认。

测试可注入 `FakeFeishuClient`，记录回复、更新和主动发送调用并模拟失败，不访问网络。
## Task 3 已实现

- 完全不依赖 LLM 的需求人正式卡片流程；
- 后端身份、角色和楼宇校验；
- 草稿、部分字段保存、我的申请、楼长候选、提交和重新提交；
- `brand`/`model` 选填，数量使用字符串；
- 保存使用 `expected_version`，正式动作使用 `action_token`；
- 跨角色通知仍只由后端 Outbox 驱动。
