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

状态：基础设施已实现；正式通知事件模板和生产幂等存储待契约冻结。

- 飞书验签/解密；
- 文本与卡片事件；
- 回复、更新、主动发送；
- 通知网关 HTTP 接口；
- 通知幂等；
- event_type RendererRegistry。

## 任务 3：需求人正式卡片

不依赖 LLM。提交后只等待后端 Outbox 通知楼长。

## 任务 4：楼长正式卡片

状态：已实现。不依赖 LLM，支持同轮 review DRAFT 保存、驳回、采购员候选选择和提交
采购员。供应商智能推荐、楼长 Agent 和黑名单不属于本任务。

## 任务 5：采购员正式卡片

实际单价、后端总价、供应商档案同步确认、提交仓库。

## 任务 6：仓库管理员正式卡片

received_quantity 和少收备注规则、确认完成。

## 任务 7：无 LLM 全流程联调

需求人、楼长、采购员和仓库管理员的确定性端到端闭环。

## 任务 8：通用智能助手核心

LLM Client、强类型意图、上下文、能力策略和故障隔离。各角色 Agent 能力从 Task 9
开始实现。

## Task 3 完成状态

需求人无 LLM 正式卡片流程已完成：楼宇确认、DRAFT 创建、字段保存、我的申请、
楼长候选、首次提交、REJECTED 修改和重新提交。楼长业务处理不在本任务范围。

## Task 4 交付状态

楼长无 LLM 正式卡片流程已实现：审核字段保存、驳回、采购员选择与提交。
