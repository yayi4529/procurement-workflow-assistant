# 开发路线 V2.1

## 任务 1：项目骨架、签名与 BackendClient

状态：已实现（待与真实后端 OpenAPI/联调样例核对精确字段）。

- Settings；
- Domain DTO；
- GatewayIdentitySigner；
- SignedBackendTransport；
- BackendClient/Fake；
- 统一错误；
- `/users/me` 与会话接口契约测试。

## 任务 2：飞书 Webhook 与通知网关

- 飞书验签/解密；
- 文本与卡片事件；
- 回复、更新、主动发送；
- 通知网关 HTTP 接口；
- 通知幂等；
- event_type RendererRegistry。

## 任务 3：需求人正式卡片

不依赖 LLM。提交后只等待后端 Outbox 通知楼长。

## 任务 4：需求人 Agent

自然语言预填、后端缺失字段追问、可选品牌型号推荐、会话恢复。

## 任务 5：楼长

同轮 review DRAFT 保存、通过/驳回完成、供应商推荐、已完成采购黑名单。

## 任务 6：采购员

实际单价、后端总价、供应商档案同步确认、提交仓库。

## 任务 7：仓库

received_quantity 和少收备注规则、确认完成。

## 任务 8：联调与可靠性

真实 HMAC、OpenAPI 契约、Outbox 通知联调、重试、监控和脱敏。
