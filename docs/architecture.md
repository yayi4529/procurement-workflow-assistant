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
