# 剩余待确认项（后端 V1.5 / 数据库 V1.4）

## 已解决

以下旧差异已统一：

- 楼长单价/总价；
- 采购员单价/总价；
- `expected_arrival_date`；
- `warranty_info`；
- `received_quantity`；
- 楼长联系人姓名、信息和链接；
- `update_supplier_profile`。

## 仍待确认

### 1. 通知网关 URL 路径

后端配置为 `NOTIFICATION_GATEWAY_URL`，但接收路径尚未冻结。

### 2. 通知事件 Schema

需冻结 event_type 列表、每种 payload、卡片模板和错误响应格式。

### 3. 通知网关生产幂等存储

网关必须按 Idempotency-Key 幂等，但外部 Agent 不直接访问采购后端 MySQL/Redis。需要确定生产存储方案。

### 4. 通知责任文字冲突

V1.5 个别流程接口仍写“Agent 侧发送提醒”，但 Outbox 与联调说明明确由后端 worker 调用通知网关。为防止双发，本项目暂以 Outbox 为唯一跨角色通知触发源，需后端最终确认。

### 5. 品牌和型号是否业务必填

数据库 V1.4 将 brand/model 设为可选，旧业务描述要求必填。当前按后端为准：可推荐、可补全，但不阻止提交。

### 6. 统计接口

采购历史接口返回明细，没有冻结统计接口。LLM 不得自行计算次数、价格区间和主要供应商。

### 7. Agent 会话与当前用户精确响应 Schema

现有 V1.5 文档冻结了接口、主要字段和行为，但没有给出所有接口的完整响应 JSON
Schema（包括字段是否必返、时间字段和分页元数据的精确命名）。Task 1 按当前文档建立了
严格模型和契约测试；接入真实后端前，需以后端 OpenAPI 或联调响应样例逐字段确认。

## Task 2 实施说明

- 通知路径继续由环境变量配置；`/internal/notifications` 仅是开发默认值。
- 生产容器未注册正式业务 Notification Renderer，等待事件与 Payload Schema 冻结。
- `MemoryNotificationDeliveryStore` 仅允许 development/test，production 会拒绝；
  生产级持久化实现仍待选择。
- `MemoryEventDedupStore` 是单进程基础实现，不具备生产级跨实例去重能力。
- 当前错误 JSON 沿用 FastAPI 结构，最终响应格式仍待联调冻结。
## Task 3 联调待确认

- V1.5 仍未提供本任务七个接口的完整响应 JSON Schema；当前采用任务所需最小严格 DTO，
  接入真实后端前需以 OpenAPI/响应样例逐字段确认。
- 正式楼长通知 `event_type` 与 payload Schema 尚未冻结，因此 Task 3 未注册生产
  Notification Renderer，也不会绕过 Outbox 主动通知楼长。
- `allowed_actions` 的实际完整枚举仍需由后端 OpenAPI 冻结；当前严格支持需求人流程使用的
  `UPDATE_APPLICANT_FIELDS`、`SUBMIT_REVIEW`、`RESUBMIT_REVIEW`。
- 驳回原因字段是否为 `rejection_reason` 仍需真实 Schema 确认；当前为可选最小字段，
  缺失时卡片不编造原因。
## Task 4 联调待确认

- 三个楼长写接口的完整响应 JSON Schema 仍需以后端 OpenAPI 或真实样例确认。
- `proposed_supplier_id` 在任务文件中列出，但契约摘要冻结字段清单未列出。
- `review_record` 嵌套结构及 `review_status` 返回位置尚未冻结。
- `allowed_actions` 中三个楼长动作的精确编码仍需后端确认。
- 正式 Outbox 通知事件类型及 Payload 仍未冻结。

## Task 5 联调待确认

- 供应商列表、详情、创建和采购字段保存的完整响应 JSON Schema 仍需以后端 OpenAPI
  或真实联调样例逐字段确认。
- `SUPPLIER_MATCH_CONFLICT` 的候选供应商具体承载位置和 Schema 尚未冻结；当前客户端
  不会自动合并，待后端冻结后再渲染冲突候选确认卡。
- 后端对不同采购员角色返回完整或脱敏银行账号的精确字段标志尚未冻结；当前采用
  `bank_account_masked` 最小严格字段，确认卡始终二次脱敏。
- 采购字段 `missing_fields` 的完整必填清单、`purchased_at` 的时区约束及供应商创建
  必填字段仍需真实契约确认。
- 采购员 `allowed_actions` 三个动作的精确编码及正式 Outbox 通知事件 Payload 尚未冻结。
