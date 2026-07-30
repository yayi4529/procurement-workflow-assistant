# 架构设计 V2.1

## 1. 三条入口

```text
飞书文本消息 ─────→ AssistantMessageHandler ─→ AssistantOrchestrator
飞书卡片事件 ─────→ CardAction/FormHandler ──→ CardActionRouter
后端 Outbox 通知 ─→ NotificationGatewayHandler ─→ FeishuClient
                                      │
                                      ▼
                                BackendClient
                                      │
                              采购后端 /api/v1
```

## 2. 调用采购后端

所有采购后端请求由可信适配层生成 HMAC 身份签名。应用层不得自行拼接签名头。

建议组件：

```text
GatewayIdentitySigner
SignedBackendTransport
HttpBackendClient
```

## 3. 通知责任

采购状态流转成功时，后端与业务事务同时写入 Outbox。本项目不得根据业务接口响应再次主动发送跨角色通知。

后端 worker 通过 HTTP 调用本项目的通知网关：

```text
NotificationGatewayHandler
→ NotificationDeliveryStore 幂等检查
→ RendererRegistry
→ FeishuClient
→ 2xx
```

## 4. 隔离规则

- 卡片正式路径不调用 LLM；
- 通知网关不调用状态流转接口；
- Agent 不直接访问 MySQL/Redis；
- 正式事实始终从后端加载；
- 后端通知失败由 Outbox 重试。

## 5. Task 2 实现调用链

```text
POST 飞书 Webhook
→ FeishuWebhookParser
→ EventDedupStore
→ BaseMessageHandler / BaseCardInteractionHandler
→ ChannelClient
→ Feishu SDK Adapter
```

```text
Backend notification_outbox worker
→ POST Notification Gateway
→ Bearer/Header 校验
→ NotificationDeliveryStore
→ NotificationRendererRegistry
→ ChannelClient
→ Feishu SDK Adapter
```

平台 JSON 和 `lark_oapi` 只存在于 `adapters/feishu`。Domain 和 Application 不依赖
FastAPI、httpx 或飞书 SDK。通知链路不持有 `BackendClient`，失败不会重新执行采购动作。
## Task 3 需求人调用链

```text
飞书卡片回调
→ EventDedupStore
→ ApplicantActionRouter
→ ApplicantWorkflowService
→ BackendClient
→ ApplicantCardFactory
→ ChannelClient.update_interaction
```

该链路不依赖 LLM、Agent Session 或具体飞书 SDK。正式提交成功后仅更新原卡片，
不根据业务响应主动通知楼长。
## Task 4 楼长调用链

```text
飞书楼长卡片回调
→ BuildingManagerActionRouter
→ BuildingManagerWorkflowService
→ BackendClient
→ BuildingManagerCardFactory
→ ChannelClient.update_interaction
```

正式动作前重新读取详情；客户端不直接发送需求人或采购员通知。

## Task 5 采购员调用链

```text
飞书采购员卡片回调
→ PurchaserActionRouter
→ PurchaserWorkflowService
→ BackendClient
→ PurchaserCardFactory
→ ChannelClient.update_interaction
```

开始采购、保存采购字段和提交仓库前均重新读取后端详情。供应商和黑名单信息只采用
后端裁剪结果，实际总价只展示后端响应；成功后不直接通知仓库管理员。

## Task 6 仓库管理员调用链

```text
飞书仓库卡片回调
→ WarehouseActionRouter
→ WarehouseWorkflowService
→ BackendClient
→ WarehouseCardFactory
→ ChannelClient.update_interaction
```

准备完成前重新读取后端详情并以后端 `fields_complete`、`allowed_actions` 和最新 version
为准。正式完成不直接通知需求人、楼长或采购员。

## Task 7 无 LLM 封板

`PROCUREMENT_LLM_ENABLED=false` 是正式流程默认值。当前容器没有 LLM 或
Assistant Orchestrator 构造路径，四角色卡片 Application Service 仅依赖
`BackendClient`，不需要 OpenAI 配置或 Agent Session。

永久测试保护四角色 card/application 不导入 LLM 或 Agent Session、正式动作不直接发
跨角色通知，以及 `NotificationGatewayService` 不依赖业务流转接口。
