# 数据中心采购流程自动化平台总体 Task 规划

> 若总体规划与某个 Task 的独立任务文档冲突，以该独立任务文档为准，并同步修订总体规划
> 及相关项目文档。

版本：V1.0  
适用仓库：`procurement-workflow-assistant`  
契约基线：

- 《数据中心采购流程自动化 Agent - 后端接口文档 V1.5》
- 《数据中心采购流程自动化 Agent - 数据库设计文档 V1.4》
- 《后端接口联调说明》（2026-07-30）
- 仓库内 `AGENTS.md`
- 仓库内 `CODEX_PROJECT_SPEC.md`

---

# 1. 项目最终目标

开发一个基于飞书卡片、采购后端和智能助手的采购流程自动化平台。

系统包含四个业务角色：

```text
APPLICANT
BUILDING_MANAGER
PURCHASER
WAREHOUSE_MANAGER
```

分别对应：

```text
需求人
楼长
采购员
仓库管理员
```

系统必须满足两个独立目标。

## 1.1 正式采购流程目标

在完全不配置 LLM、LLM 超时、LLM 不可用或 Agent 会话丢失时，用户仍然能够通过飞书卡片完成：

```text
需求人创建采购申请
→ 提交楼长审核
→ 楼长填写审核信息并通过或驳回
→ 采购员填写实际采购信息
→ 提交仓库管理员
→ 仓库管理员填写入库信息
→ 确认入库
→ 采购流程 COMPLETED
```

这条链路是项目的核心交付目标。

## 1.2 智能助手目标

在正式卡片流程已经稳定后，为四个角色增加智能辅助：

```text
需求人 Agent
楼长 Agent
采购员 Agent
仓库管理员 Agent
```

但不是开发四套独立 Agent。

正确设计是：

```text
一个 ProcurementAssistant
→ 根据当前用户角色
→ 当前采购单
→ 当前卡片
→ 当前咨询字段
→ 后端 allowed_actions
→ 启用相应角色能力
```

Agent 只负责：

- 理解自然语言；
- 查询；
- 解释；
- 推荐；
- 生成候选预填值；
- 总结后端返回的事实；
- 帮助用户正确填写卡片。

Agent 不负责正式状态流转。

---

# 2. 不可违反的系统原则

## 2.1 后端是正式事实来源

以下信息必须以后端响应为准：

- 当前用户身份；
- 员工 ID；
- 角色；
- 楼宇；
- 正式采购字段；
- 缺失字段；
- 下一缺失字段；
- 当前状态；
- 当前处理人；
- 合法处理人候选；
- 允许动作；
- `version`；
- 黑名单状态；
- 采购历史；
- 统计数字；
- 正式操作结果。

飞书卡片、Agent 和 Redis 均不得维护另一套权威状态。

## 2.2 卡片负责正式业务操作

正式操作必须由用户点击卡片按钮或提交卡片表单触发，包括：

- 保存需求人字段；
- 提交楼长；
- 重新提交楼长；
- 保存楼长字段；
- 驳回；
- 提交采购员；
- 开始采购；
- 保存采购字段；
- 提交仓库；
- 保存入库字段；
- 确认入库；
- 加入供应商黑名单；
- 解除供应商黑名单。

## 2.3 Agent 不直接执行正式操作

Agent 不得直接执行：

```text
提交
通过
驳回
转交
入库
拉黑
解除黑名单
```

Agent 可以生成确认卡片，但必须由用户点击确认。

## 2.4 全流程必须独立于 LLM

以下测试必须长期保留：

```text
LLMClient 完全不可用
→ 四角色仍然可以通过卡片完成完整采购流程
```

## 2.5 数据访问边界

本项目：

- 不直接访问采购后端 MySQL；
- 不直接访问采购后端 Redis；
- 只通过采购后端 HTTP API；
- Agent 会话通过后端 Agent Session API 管理；
- 正式采购数据只通过业务接口写入。

## 2.6 并发与幂等

- 所有字段修改携带 `expected_version`；
- 所有正式动作携带 `action_token`；
- 同一次用户动作重试复用相同 `action_token`；
- 飞书事件需要事件幂等；
- 通知网关需要 `Idempotency-Key` 幂等；
- 通知失败不得重新执行业务动作。

## 2.7 通知责任

正式跨角色通知采用：

```text
采购业务事务
→ notification_outbox
→ 后端 Worker
→ 本项目通知网关
→ 飞书消息或卡片
```

业务接口成功响应中的 `platform_identities` 不应再触发第二次跨角色通知，避免双发。

---

# 3. 总体开发阶段

整个项目建议拆分为 13 个 Task。

```text
阶段 A：基础设施
Task 1～2

阶段 B：无 LLM 正式采购全流程
Task 3～7

阶段 C：四角色智能助手
Task 8～12

阶段 D：生产联调和上线准备
Task 13
```

关键里程碑：

```text
Task 7 完成
→ 全采购流程已经不依赖 LLM

Task 12 完成
→ 四个角色都具备 Agent 辅助能力

Task 13 完成
→ 全链路可联调、可观测、可部署
```

---

# 4. Task 总览

| Task | 名称 | 核心结果 | LLM |
|---|---|---|---|
| Task 1 | 后端契约基础 | HMAC、BackendClient、Agent Session、Fake、Health | 不使用 |
| Task 2 | 飞书与通知基础设施 | Webhook、通用卡片、Channel、通知网关 | 不使用 |
| Task 3 | 需求人正式卡片流程 | 创建、保存、选择楼长、提交审核 | 不使用 |
| Task 4 | 楼长正式卡片流程 | 审核字段、驳回、提交采购员 | 不使用 |
| Task 5 | 采购员正式卡片流程 | 采购字段、供应商资料、提交仓库 | 不使用 |
| Task 6 | 仓库管理员正式卡片流程 | 入库字段、确认完成 | 不使用 |
| Task 7 | 无 LLM 全流程联调 | 四角色端到端闭环 | 明确禁用 |
| Task 8 | 通用智能助手核心 | LLM Client、意图、上下文、能力策略 | 使用 |
| Task 9 | 需求人 Agent 能力 | 自然语言创建、追问、产品推荐、预填 | 使用 |
| Task 10 | 楼长 Agent 能力 | 供应商、历史价格、合同、黑名单辅助 | 使用 |
| Task 11 | 采购员 Agent 能力 | 供应商财务资料查询与采购预填 | 使用 |
| Task 12 | 仓库管理员 Agent 能力 | 入库查询、解释和预填 | 使用 |
| Task 13 | 全链路可靠性与生产化 | 真实联调、监控、重试、部署验收 | 可选启用 |

---

# 5. Task 1：后端契约基础

状态：

```text
已完成
```

推荐分支：

```text
feature/1-backend-contract-foundation
```

## 5.1 目标

建立所有后续任务共用的后端访问基础。

## 5.2 已完成范围

- 项目 `src` layout；
- 强类型 Settings；
- `PlatformIdentity`；
- 稳定角色和平台枚举；
- HMAC-SHA256 `GatewayIdentitySigner`；
- `SignedBackendTransport`；
- 后端统一响应 Envelope；
- 错误映射；
- `BackendClient` Protocol；
- `HttpBackendClient`；
- `FakeBackendClient`；
- Agent 会话接口；
- `/health/live`；
- `/health/ready`；
- Ruff、mypy strict、pytest。

## 5.3 后端接口

```text
GET  /api/v1/users/me

POST /api/v1/agent/conversations/active
POST /api/v1/agent/conversations/{id}/messages
GET  /api/v1/agent/conversations/{id}/messages
GET  /api/v1/agent/conversations/{id}/state
PUT  /api/v1/agent/conversations/{id}/state
POST /api/v1/agent/conversations/{id}/snapshot
POST /api/v1/agent/conversations/{id}/complete
```

## 5.4 完成标准

Task 1 已完成，不在后续任务中重新实现。

---

# 6. Task 2：飞书接入、通用卡片与通知网关

状态：

```text
下一项任务
```

推荐分支：

```text
feature/2-feishu-notification-foundation
```

依赖：

```text
Task 1
```

## 6.1 目标

建立后续所有角色共同使用的飞书与通知基础设施。

## 6.2 开发范围

### 飞书 Webhook

- Challenge；
- 验签；
- 解密；
- 私聊文本事件；
- 卡片回调；
- 统一事件模型；
- 事件去重；
- 未知事件处理。

### 平台无关卡片

- `InteractionView`；
- 文本；
- Markdown；
- 键值信息；
- 输入框；
- 下拉框；
- 日期选择；
- 按钮；
- 飞书 Renderer。

### Channel

- 回复文本；
- 回复卡片；
- 更新原卡片；
- 主动发送文本；
- 主动发送卡片；
- `FakeFeishuClient`。

### 通知网关

```text
Backend Outbox Worker
→ Notification Gateway
→ Idempotency Store
→ Renderer Registry
→ FeishuChannelClient
```

包括：

- Bearer Token；
- `Idempotency-Key`；
- `X-Notification-Id`；
- Payload 指纹；
- 重复投递；
- 冲突处理；
- 发送失败返回非 2xx。

## 6.3 不做

- 不做正式采购卡片；
- 不做采购业务状态流转；
- 不接 LLM；
- 不创建未经后端确认的正式通知模板；
- 不直接访问数据库或 Redis。

## 6.4 验收标准

- 飞书私聊文本可被正确解析；
- 测试卡片可以回复和更新；
- 通知网关可以接收测试事件并发送测试卡片；
- 相同通知重复请求只发送一次；
- Task 1 全部测试不回归。

---

# 7. Task 3：需求人正式卡片流程

推荐分支：

```text
feature/3-applicant-card-flow
```

依赖：

```text
Task 1
Task 2
```

## 7.1 目标

在完全不使用 LLM 的情况下，需求人可以通过卡片创建并提交采购申请。

## 7.2 正式流程

```text
用户打开采购中心
→ 获取当前用户
→ 确认需求人角色
→ 选择或自动确定楼宇
→ 创建 DRAFT
→ 展示需求人表单卡片
→ 保存字段
→ 获取后端 missing_fields
→ 字段完整
→ 查询楼长候选
→ 展示提交确认卡片
→ 用户确认提交
→ PENDING_REVIEW
→ 后端写 notification_outbox
```

## 7.3 需求人卡片字段

按后端 V1.5 当前规则：

```text
device_profession
device_name
quantity
unit
application_reason
brand
model
applicant_remark
```

注意：

- 当前后端将 `brand` 和 `model` 设为可选；
- 前端不能自行把它们当作阻止提交的必填项；
- 是否完整以后端 `missing_fields` 为准。

## 7.4 后端接口

```text
GET   /api/v1/users/me
POST  /api/v1/requirements
PATCH /api/v1/requirements/{id}/applicant-fields
GET   /api/v1/requirements/{id}
GET   /api/v1/requirements/{id}/handler-candidates
POST  /api/v1/requirements/{id}/submit-review
POST  /api/v1/requirements/{id}/resubmit-review
```

## 7.5 卡片

至少实现：

- 采购中心首页；
- 新建采购草稿；
- 保存结果；
- 缺失字段提示；
- 楼长选择；
- 提交审批确认；
- 已提交状态；
- 被驳回后的修改和重新提交。

## 7.6 不做

- 不做自然语言字段提取；
- 不做品牌型号推荐；
- 不接 LLM；
- 不做楼长审核卡片业务。

## 7.7 验收标准

```text
没有配置 LLM
→ 需求人可以创建并提交 PENDING_REVIEW
```

---

# 8. Task 4：楼长正式卡片流程

推荐分支：

```text
feature/4-building-manager-card-flow
```

依赖：

```text
Task 3
```

## 8.1 目标

楼长可以在不使用 LLM 的情况下完成审核、驳回或提交采购员。

## 8.2 正式流程

```text
楼长收到 Outbox 推送的待审核卡片
→ 打开采购详情
→ 后端校验角色、楼宇和当前处理人
→ 保存楼长审核字段
→ 字段完整
→ 选择采购员
→ 确认提交采购员
→ PENDING_PURCHASE
```

驳回：

```text
楼长输入驳回原因
→ 确认驳回
→ REJECTED
→ 后端 Outbox 通知需求人
```

## 8.3 楼长字段

```text
proposed_supplier_id
supplier_contact_name
supplier_contact_info
supplier_link
estimated_unit_price
estimated_total_price
need_contract
contract_type
payment_method
expected_arrival_date
warranty_info
review_remark
```

规则：

- `estimated_total_price` 以后端计算和校验结果为准；
- `need_contract=true` 时 `contract_type` 必填；
- 同一审核轮次首次保存创建 DRAFT review；
- 后续保存更新同一条；
- 通过或驳回将同一条更新为 COMPLETED；
- 重新提交后才创建新的审核轮次。

## 8.4 后端接口

```text
GET   /api/v1/requirements/{id}
PATCH /api/v1/requirements/{id}/review-fields
POST  /api/v1/requirements/{id}/reject
GET   /api/v1/requirements/{id}/handler-candidates
POST  /api/v1/requirements/{id}/submit-purchaser
```

## 8.5 卡片

至少实现：

- 待审核卡片；
- 楼长审核表单；
- 保存结果；
- 提交采购员确认；
- 驳回确认；
- 已通过结果；
- 已驳回结果；
- 并发冲突刷新。

## 8.6 不做

- 不做供应商智能推荐；
- 不做历史价格智能总结；
- 不接 LLM；
- 不在本 Task 实现供应商黑名单对话辅助。

## 8.7 验收标准

```text
没有配置 LLM
→ 楼长可以通过卡片驳回
或
→ 楼长可以通过卡片提交采购员
```

---

# 9. Task 5：采购员正式卡片流程

推荐分支：

```text
feature/5-purchaser-card-flow
```

依赖：

```text
Task 4
```

## 9.1 目标

采购员可以在不使用 LLM 的情况下完成实际采购信息填写并提交仓库。

## 9.2 正式流程

```text
采购员收到待采购卡片
→ 开始采购
→ 选择或创建供应商
→ 填写实际采购信息
→ 保存字段
→ 选择仓库管理员
→ 确认提交仓库
→ PENDING_WAREHOUSE
```

## 9.3 采购员字段

```text
supplier_id
supplier_tax_number
bank_name
bank_account
registered_address
contract_contact_info
actual_unit_price
actual_total_price
tax_rate
purchased_at
purchase_remark
update_supplier_profile
```

规则：

- `actual_total_price` 以后端计算和校验为准；
- 本次采购保存供应商资料快照；
- 只有采购员明确确认 `update_supplier_profile=true` 时才更新供应商档案；
- 银行账号属于敏感字段；
- 非采购员角色默认只显示脱敏账号。

## 9.4 后端接口

```text
POST  /api/v1/requirements/{id}/start-purchase
GET   /api/v1/suppliers
GET   /api/v1/suppliers/{supplier_id}
POST  /api/v1/suppliers
PATCH /api/v1/requirements/{id}/purchase-fields
GET   /api/v1/requirements/{id}/handler-candidates
POST  /api/v1/requirements/{id}/submit-warehouse
```

## 9.5 卡片

至少实现：

- 待采购卡片；
- 开始采购；
- 供应商搜索和选择；
- 新供应商信息；
- 采购执行表单；
- 是否同步供应商档案确认；
- 提交仓库确认；
- 已提交结果。

## 9.6 不做

- 不做自然语言供应商查询；
- 不做智能预填；
- 不接 LLM；
- 不做仓库正式入库。

## 9.7 验收标准

```text
没有配置 LLM
→ 采购员可以通过卡片提交 PENDING_WAREHOUSE
```

---

# 10. Task 6：仓库管理员正式卡片流程

推荐分支：

```text
feature/6-warehouse-card-flow
```

依赖：

```text
Task 5
```

## 10.1 目标

仓库管理员可以在不使用 LLM 的情况下完成一次性入库并结束采购流程。

## 10.2 正式流程

```text
仓库管理员收到待入库卡片
→ 查看采购信息
→ 填写仓库位置
→ 填写实际入库数量
→ 填写备注
→ 保存
→ 确认入库
→ COMPLETED
→ current_handler = null
```

## 10.3 入库字段

```text
warehouse_location
received_quantity
receipt_remark
```

规则：

- 当前不支持分批入库；
- `received_quantity` 必须大于 0；
- 可以小于、等于或大于申请数量；
- 少于申请数量时 `receipt_remark` 必填。

## 10.4 后端接口

```text
GET   /api/v1/requirements/{id}
PATCH /api/v1/requirements/{id}/warehouse-fields
POST  /api/v1/requirements/{id}/complete
```

## 10.5 卡片

至少实现：

- 待入库卡片；
- 入库表单；
- 少收提示；
- 保存结果；
- 确认完成；
- 已完成结果。

## 10.6 不做

- 不做库位智能推荐；
- 不做自然语言查询；
- 不接 LLM。

## 10.7 验收标准

```text
没有配置 LLM
→ 仓库管理员可以完成采购流程
→ status = COMPLETED
```

---

# 11. Task 7：无 LLM 全流程联调与封板

推荐分支：

```text
feature/7-no-llm-end-to-end
```

依赖：

```text
Task 3
Task 4
Task 5
Task 6
```

## 11.1 目标

在引入 LLM 前，证明正式采购流程已经完整、稳定、可测试。

## 11.2 端到端流程

```text
需求人
→ 创建 DRAFT
→ 保存字段
→ 提交楼长

楼长
→ 保存审核字段
→ 提交采购员

采购员
→ 开始采购
→ 保存采购字段
→ 提交仓库

仓库管理员
→ 保存入库字段
→ 确认完成

最终
→ COMPLETED
```

必须额外覆盖驳回分支：

```text
需求人提交
→ 楼长驳回
→ 需求人修改
→ 重新提交
→ 楼长通过
```

## 11.3 强制关闭 LLM

测试环境中：

```text
LLM_ENABLED=false
```

或不配置任何 LLM 密钥。

项目仍应完整运行。

## 11.4 联调范围

- HMAC 身份签名；
- 飞书 Webhook；
- 卡片提交；
- `expected_version`；
- `action_token`；
- 事件重复；
- 通知 Outbox；
- 通知网关；
- 通知幂等；
- 原卡片更新；
- 角色和楼宇权限；
- 当前处理人；
- 敏感字段裁剪；
- 时间线；
- 错误提示。

## 11.5 失败场景

必须测试：

- 旧版本提交；
- 重复点击；
- 非当前处理人；
- 楼长跨楼宇；
- 非法下一处理人；
- 缺少字段；
- 通知失败；
- 飞书更新失败；
- 同一 Outbox 通知重复投递；
- 后端超时；
- 用户刷新旧卡片。

## 11.6 核心验收标准

```text
LLMClient 不存在或不可用
→ 完整四角色采购流程仍然成功
```

Task 7 完成后，正式采购核心功能才算开发完成。

---

# 12. Task 8：四角色共用智能助手核心

推荐分支：

```text
feature/8-assistant-core
```

依赖：

```text
Task 7
```

## 12.1 目标

建立四个角色共同使用的一套智能助手基础，而不是四个独立 Agent。

## 12.2 架构

```text
AssistantMessageHandler
→ Agent Session
→ AssistantContextBuilder
→ RoleCapabilityPolicy
→ IntentExtractor
→ AssistantOrchestrator
→ 确定性 Application Service
→ BackendClient
→ 文本或预填建议卡片
```

## 12.3 核心模块

- OpenAI-compatible `LLMClient`；
- 强类型消息映射；
- 强类型工具 Schema；
- 结构化输出 Parser；
- `AssistantOrchestrator`；
- `AssistantContextBuilder`；
- `RoleCapabilityPolicy`；
- Agent Session 加载、消息写入、状态更新、快照和完成；
- `CARD_HELP` 上下文；
- LLM 失败降级；
- 超时；
- 最大轮次；
- Prompt 安全约束。

## 12.4 统一意图

建议：

```text
SEARCH_RECORDS
QUERY_STATUS
PROCESS_GUIDE
SEARCH_CATALOG
PREFILL_FORM
SUMMARIZE_RESULTS
CARD_HELP
PREPARE_BLACKLIST
```

## 12.5 角色能力策略

```text
APPLICANT
→ 需求预填、商品推荐、状态查询、流程解释

BUILDING_MANAGER
→ 历史采购、供应商推荐、审核帮助、黑名单准备

PURCHASER
→ 供应商资料、采购字段帮助、采购状态查询

WAREHOUSE_MANAGER
→ 入库详情、字段解释、历史库位查询
```

## 12.6 不做

本 Task 不完成具体角色的全部业务能力，只建立共用框架和测试 Fake。

## 12.7 验收标准

- 同一 Assistant 可以识别当前角色；
- 不同角色获得不同能力；
- Agent 不能调用正式提交动作；
- LLM 不可用时返回降级提示并引导用户继续使用卡片；
- Task 7 无 LLM 全流程测试继续通过。

---

# 13. Task 9：需求人 Agent 能力

推荐分支：

```text
feature/9-applicant-assistant
```

依赖：

```text
Task 3
Task 8
```

## 13.1 目标

让需求人可以通过自然语言快速创建和完善采购草稿。

## 13.2 能力

- 自然语言提取候选字段；
- 创建或关联 DRAFT；
- 保存候选字段；
- 根据后端 `missing_fields` 和 `next_missing_field` 追问；
- 一次只追问一个字段；
- 设备专业、品牌、型号推荐；
- 最多展示 3 个候选；
- 用户回复“第一个”等序号；
- 预填需求人卡片；
- 查询申请状态；
- 查询历史采购；
- 解释字段；
- 卡片中的“问智能助手”。

## 13.3 强制规则

- 字段完整性以后端为准；
- `brand`、`model` 当前为可选；
- Agent 不能直接提交楼长；
- 用户必须在提交确认卡片点击；
- 推荐必须来自后端；
- 用户选择候选后重新校验；
- Redis 候选不是正式事实。

## 13.4 验收标准

```text
自然语言描述不完整
→ Agent 逐项追问
→ 后端草稿逐步更新
→ 用户获得预填正式卡片
→ 最终仍由用户点击提交
```

---

# 14. Task 10：楼长 Agent 能力

推荐分支：

```text
feature/10-building-manager-assistant
```

依赖：

```text
Task 4
Task 8
```

## 14.1 目标

为楼长审核卡片提供查询、推荐、解释和预填辅助。

## 14.2 能力

- 查询同类采购记录；
- 查询历史预计价格；
- 查询历史供应商；
- 推荐供应商；
- 查询供应商黑名单状态；
- 解释合同类型；
- 解释付款方式；
- 查询历史质保；
- 预填楼长审核卡片；
- 协助整理驳回原因；
- 协助准备供应商黑名单信息；
- 状态和时间线查询；
- “问智能助手”。

## 14.3 黑名单辅助

Agent 可以：

- 定位采购单；
- 查询关联供应商；
- 收集原因；
- 收集类型；
- 收集期限；
- 生成确认卡片。

正式拉黑仍由卡片确认。

黑名单限制：

- 只能由楼长操作；
- 采购申请必须已 `COMPLETED`；
- 模糊名称不能直接执行；
- 永久和有限期规则由后端校验。

## 14.4 验收标准

- 楼长可以问供应商和历史价格；
- Agent 生成预填建议；
- 用户点击应用后重新读取最新 version；
- Agent 不能驳回、通过或拉黑；
- Task 4 无 LLM 卡片流程继续通过。

---

# 15. Task 11：采购员 Agent 能力

推荐分支：

```text
feature/11-purchaser-assistant
```

依赖：

```text
Task 5
Task 8
```

## 15.1 目标

帮助采购员查询供应商资料并预填采购执行卡片。

## 15.2 能力

- 搜索供应商；
- 查询税号；
- 查询开户行；
- 查询银行账号；
- 查询注册地址；
- 查询合同联系方式；
- 查询历史实际价格；
- 查询税率历史参考；
- 预填采购执行卡片；
- 解释供应商档案同步；
- 查询采购状态和时间线；
- “问智能助手”。

## 15.3 敏感数据

- 后端负责字段裁剪；
- 只有采购员和管理员可以查看完整财务资料；
- Agent 不得扩大数据权限；
- 日志不得记录完整银行账号；
- 对话历史不得长期保存完整敏感财务数据。

## 15.4 强制规则

- 模糊供应商名称只返回候选；
- 必须明确 `supplier_id`；
- `update_supplier_profile` 不得由 Agent 自动勾选；
- 正式保存必须用户确认；
- 正式提交仓库必须卡片点击。

## 15.5 验收标准

```text
采购员询问供应商资料
→ 后端返回授权数据
→ Agent 生成预填建议
→ 用户应用到卡片
→ 后端正式保存
```

---

# 16. Task 12：仓库管理员 Agent 能力

推荐分支：

```text
feature/12-warehouse-assistant
```

依赖：

```text
Task 6
Task 8
```

## 16.1 目标

帮助仓库管理员查询采购信息、理解入库规则并预填入库卡片。

## 16.2 能力

- 查询采购单详情；
- 查询申请数量；
- 查询供应商；
- 查询采购员；
- 解释入库字段；
- 提示少收备注规则；
- 查询历史库位；
- 预填仓库位置；
- 预填备注建议；
- 查询状态和时间线；
- “问智能助手”。

## 16.3 能力限制

- 只有后端提供历史库位查询时才能推荐；
- 没有接口时明确说明暂不支持；
- 不得虚构仓库位置；
- 不得自动决定入库数量；
- 不得直接确认入库；
- 不得结束采购流程。

## 16.4 验收标准

- 仓库管理员可以问当前采购详情；
- Agent 可以解释少收规则；
- 后端有数据时可以提供库位候选；
- 正式完成仍必须卡片确认；
- Task 6 无 LLM 卡片流程继续通过。

---

# 17. Task 13：全链路可靠性、真实联调与生产化

推荐分支：

```text
feature/13-production-readiness
```

依赖：

```text
Task 1～12
```

## 17.1 目标

将完整系统从开发可用提升到联调、部署和生产验收状态。

## 17.2 后端联调

- 使用真实后端 OpenAPI；
- 确认所有 DTO；
- 确认所有错误码；
- 确认通知网关 URL；
- 冻结 `event_type`；
- 冻结通知 Payload Schema；
- 冻结通知错误响应；
- 确认通知责任不双发；
- 确认 Agent Session 响应模型；
- 确认统计接口。

## 17.3 飞书联调

- 飞书应用权限；
- Webhook；
- Challenge；
- 事件加密；
- 私聊消息；
- 卡片表单；
- 卡片更新；
- 主动通知；
- 多角色身份；
- 多楼宇用户；
- 飞书回调重试；
- 飞书限流。

## 17.4 可靠性

- 事件幂等生产存储；
- 通知幂等生产存储；
- 超时；
- 重试；
- 熔断；
- 限流；
- 并发；
- 旧卡片；
- 版本冲突；
- 重复动作；
- Agent Session 恢复；
- LLM 降级；
- 通知补发；
- 失败告警。

## 17.5 可观测性

- `trace_id`；
- `request_id`；
- notification ID；
- dedup key；
- action token；
- 延迟指标；
- 后端错误码；
- 飞书错误码；
- Agent 调用耗时；
- LLM Token 使用量；
- 降级次数；
- 通知重试次数；
- 日志脱敏。

## 17.6 安全

- Secret 管理；
- HMAC Secret；
- 飞书 App Secret；
- Notification Token；
- LLM API Key；
- 银行账号脱敏；
- 日志脱敏；
- Prompt 注入防护；
- Agent 工具白名单；
- 数据权限；
- 生产禁止 TEST_PLATFORM；
- 生产禁止内存幂等 Store。

## 17.7 部署

根据实际部署方式完成：

- Dockerfile；
- 生产环境变量说明；
- 反向代理；
- HTTPS；
- 回调公网地址或内网网关；
- 进程启动命令；
- Health/Readiness；
- 日志目录；
- 启停和回滚；
- 部署检查清单。

## 17.8 最终验收

### 无 LLM 验收

```text
关闭 LLM
→ 四角色完整采购流程成功
```

### 有 LLM 验收

```text
四个角色均可点击“问智能助手”
→ 获取对应角色的查询、解释、推荐和预填帮助
→ 正式动作仍由卡片完成
```

### 故障验收

```text
LLM 超时
→ 卡片流程不受影响

Agent Redis 状态丢失
→ 正式采购数据不丢失

通知失败
→ 后端业务不回滚
→ Outbox 可以重试

用户重复点击
→ 正式动作不重复执行
```

---

# 18. Task 之间的依赖关系

```text
Task 1
  ↓
Task 2
  ↓
Task 3
  ↓
Task 4
  ↓
Task 5
  ↓
Task 6
  ↓
Task 7  ← 无 LLM 正式流程封板
  ↓
Task 8  ← 通用 Agent 核心
  ├── Task 9   需求人 Agent
  ├── Task 10  楼长 Agent
  ├── Task 11  采购员 Agent
  └── Task 12  仓库管理员 Agent
          ↓
       Task 13
```

Task 9～12 在 Task 8 完成后可以根据团队人数并行开发，但每个分支必须避免同时修改同一公共核心模块。

---

# 19. 推荐 Git 分支

```text
feature/1-backend-contract-foundation
feature/2-feishu-notification-foundation
feature/3-applicant-card-flow
feature/4-building-manager-card-flow
feature/5-purchaser-card-flow
feature/6-warehouse-card-flow
feature/7-no-llm-end-to-end
feature/8-assistant-core
feature/9-applicant-assistant
feature/10-building-manager-assistant
feature/11-purchaser-assistant
feature/12-warehouse-assistant
feature/13-production-readiness
```

推荐提交信息：

```text
feat: establish backend contract foundation
feat: add feishu and notification infrastructure
feat: add applicant card workflow
feat: add building manager card workflow
feat: add purchaser card workflow
feat: add warehouse card workflow
test: verify no-llm procurement workflow
feat: add shared procurement assistant core
feat: add applicant assistant capabilities
feat: add building manager assistant capabilities
feat: add purchaser assistant capabilities
feat: add warehouse assistant capabilities
feat: harden production integration
```

---

# 20. 每个 Task 的统一开发要求

开始前：

```bash
git status
git branch --show-current
git log -5 --oneline
```

要求：

1. 阅读 `AGENTS.md`；
2. 阅读 `CODEX_PROJECT_SPEC.md`；
3. 阅读相关 docs；
4. 确认前一个 Task 已形成基线提交；
5. 创建新功能分支；
6. 先写或补测试；
7. 不直接修改远程资源；
8. 未经允许不 push；
9. 未经允许不创建 PR；
10. 发现接口冲突时停止猜测并记录。

完成前：

```bash
ruff format .
ruff format --check .
ruff check .
mypy src
pytest -q
git diff --check
git status --short
```

---

# 21. 每个 Task 的统一汇报格式

## 1. 开发前状态

- 原分支；
- 原提交；
- 工作区；
- 新分支。

## 2. 任务理解

- 本次目标；
- 本次不做；
- 依赖接口。

## 3. 实现结果

- Domain；
- Port；
- Application；
- Adapter；
- Interface；
- DI；
- Tests；
- Docs。

## 4. 文件变更

- 新增；
- 修改；
- 删除。

## 5. 调用链

说明从飞书入口到后端或从 Outbox 到飞书的完整链路。

## 6. 后端接口

列出本 Task 实际使用的全部接口。

## 7. 测试结果

提供真实命令和输出摘要。

## 8. Git 状态

- 当前分支；
- 是否提交；
- 是否推送；
- 是否创建 PR；
- 工作区是否干净。

## 9. 已知限制

只写真实限制。

## 10. 待确认项

不得自行填补后端未冻结的契约。

---

# 22. 项目完成判定

项目不能以“Agent 能回答问题”作为完成标准。

必须同时满足以下条件。

## 22.1 正式采购流程完成

```text
需求人
→ 楼长
→ 采购员
→ 仓库管理员
→ COMPLETED
```

完全不依赖 LLM。

## 22.2 四角色 Agent 完成

所有角色均可在卡片中点击：

```text
[问智能助手]
```

并在当前飞书机器人私聊窗口获得与角色匹配的帮助。

## 22.3 正式动作受控

所有正式动作：

- 由用户明确确认；
- 由后端验证身份、权限、状态和版本；
- 使用 `action_token`；
- 记录操作日志；
- 不由 LLM 直接执行。

## 22.4 故障隔离完成

- LLM 故障不影响正式流程；
- Redis 会话故障不影响正式数据；
- 飞书通知故障不回滚业务；
- 重复事件不重复处理；
- 重复通知不重复发送；
- 重复正式操作不重复执行。

---

# 23. 当前项目进度

当前状态：

```text
Task 1：已完成
Task 2：待开发
Task 3～5：已完成
Task 6～13：待开发
```

当前最重要的近期目标：

```text
先完成 Task 2
→ 再连续完成 Task 3～6
→ 通过 Task 7 验证完整无 LLM 流程
→ 之后再接入四角色 Agent
```

这是本项目最稳妥的开发顺序。
## Task 3 交付状态

需求人正式卡片流程已交付。验收以 FakeBackendClient 从 DRAFT 进入
PENDING_REVIEW、以及 REJECTED 使用原采购单重新提交为准，不配置 LLM。
## Task 4 交付状态

楼长无 LLM 正式卡片流程已交付：PENDING_REVIEW 保存同轮 DRAFT review、驳回至
REJECTED，或选择合法采购员并提交至 PENDING_PURCHASE。跨角色通知仅由后端 Outbox
驱动。

## Task 5 交付状态

采购员无 LLM 正式卡片流程已交付：PENDING_PURCHASE 开始采购、供应商搜索/选择/创建、
采购字段与供应商快照保存、后端实际总价、档案同步明确确认、仓库管理员候选选择，
并提交至 PENDING_WAREHOUSE。跨角色通知仅由后端 Outbox 驱动。
