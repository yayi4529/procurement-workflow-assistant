# 采购流程自动化平台 Codex 开发总规范

> 若本总规范中的 Task 编号或交付范围与对应独立任务文档冲突，以独立任务文档为准；
> 架构、安全和后端事实来源等强制边界仍必须遵守，并应同步修订项目文档。

版本：V2.1
用途：新建仓库，从零开发
系统定位：基于飞书卡片、智能助手和通知网关的采购流程自动化平台
契约基线：后端接口 V1.5、数据库设计 V1.4、后端接口联调说明（2026-07-30）

---

## 1. 本项目的最终定位

本项目不是“由 Agent 驱动采购流程”的系统。

本项目的正确定位是：

> 采购流程自动化系统，提供飞书卡片正式操作入口和 Agent 智能交互入口。

系统包含四个业务角色：

- `APPLICANT`：需求人；
- `BUILDING_MANAGER`：楼长；
- `PURCHASER`：采购员；
- `WAREHOUSE_MANAGER`：仓库管理员。

智能助手不是采购流程的必经路径。

正式采购流程必须在以下情况发生时仍然能够完整运行：

- 未配置大模型；
- 大模型接口超时；
- Agent 会话 Redis 缓存丢失；
- 用户从未使用自然语言入口。

正式流程由飞书卡片和后端业务接口完成。

---

## 2. 最高优先级架构原则

### 2.1 卡片负责正式业务操作

飞书卡片负责：

- 展示后端正式字段；
- 用户填写和修改正式字段；
- 用户确认；
- 触发提交、审批、驳回、流转、入库和黑名单等确定性操作；
- 更新原卡片；
- 正式动作只调用采购后端，不根据业务响应自行重复发送跨角色通知。

跨角色任务通知由采购后端在业务事务内写入 `notification_outbox`，再由后端后台任务异步调用本项目提供的平台无关通知网关。本项目的通知网关负责把通知渲染为飞书文本或卡片并发送。

### 2.2 Agent 负责辅助

Agent 只负责：

- 自然语言理解；
- 将自然语言转换为结构化查询条件；
- 快速预填采购草稿；
- 一次追问一个缺失字段；
- 根据后端推荐接口展示最多 3 个候选；
- 查询采购状态；
- 查询历史记录；
- 查询商品、品牌、型号和供应商；
- 解释字段和采购流程；
- 基于后端确定数据生成自然语言总结；
- 在用户填写卡片时提供帮助。

### 2.3 后端是唯一事实来源

以下内容全部以后端返回为准：

- 用户身份；
- 角色；
- 楼宇；
- 正式采购字段；
- 正式采购状态；
- 当前处理人；
- 缺失字段；
- 下一缺失字段；
- 字段是否完整；
- 允许动作；
- 业务版本；
- 供应商资料；
- 黑名单状态；
- 统计数字；
- 正式业务操作结果。

Agent 和卡片均不得维护另一套权威业务状态。

### 2.4 Redis 只保存 Agent 会话

Agent 实时会话由后端通过 Redis 管理。

Redis 可以保存：

- 当前关联的采购单 ID；
- 最近自然语言意图；
- 最近查询条件；
- 最近商品或供应商候选引用；
- 当前卡片类型；
- 当前咨询字段；
- 最近消息；
- 对话摘要；
- 是否正在等待用户回答；
- 短期预填建议。

Redis 不能作为以下信息的唯一来源：

- 正式采购字段；
- 正式采购状态；
- 当前处理人；
- 正式版本；
- 审批结果；
- 黑名单结果；
- 已完成业务动作。

### 2.5 楼宇来源

楼宇来源于飞书通讯录或企业组织数据，并由后端同步、映射和校验。

本项目通过：

```http
GET /api/v1/users/me
```

获取当前员工、角色和楼宇。

禁止让 LLM 推断 `building_id`。

楼宇处理规则：

- 只有一个有效楼宇：自动预填；
- 多个楼宇且存在唯一主要楼宇：卡片默认预选；
- 多个楼宇且无唯一默认：卡片要求用户选择；
- 后端在创建草稿和正式提交时再次校验。

---

## 3. 新仓库建议

推荐仓库名：

```text
procurement-workflow-assistant
```

推荐 Python 包名：

```text
procurement_platform
```

建议技术栈：

- Python 3.11+
- FastAPI
- Pydantic 2
- httpx
- lark-oapi
- OpenAI-compatible async client
- pytest
- pytest-asyncio
- mypy strict
- Ruff

本项目不得直接访问 MySQL。

Agent 会话默认通过后端 Agent 会话接口管理，不直接连接 Redis。若后续明确由本项目直接管理 Redis，必须新增独立 Adapter，不能污染领域和应用层。

---

## 4. 三条相互隔离的入口

### 4.1 正式卡片入口

```text
飞书卡片事件
→ Webhook 验签与解密
→ CardActionHandler / CardFormHandler
→ CardActionRouter
→ 对应角色 Application Service
→ BackendClient
→ 后端 REST API
→ 根据后端结果更新或推送卡片
```

该调用链禁止引用：

- `LLMClient`
- `AssistantOrchestrator`
- `IntentExtractor`
- 模型 Prompt
- Agent Tool Loop

### 4.2 智能助手入口

```text
飞书文本消息
→ Webhook 验签与解密
→ AssistantMessageHandler
→ 加载 Agent 会话
→ AssistantOrchestrator
→ LLM 输出强类型 AssistantRequest
→ 确定性查询、预填、状态或指引服务
→ BackendClient
→ 文本回复或预填建议卡片
→ 更新 Agent 会话
```

### 4.3 后端通知网关入口

```text
采购后端 notification_outbox worker
→ HTTP POST 通知网关
→ NotificationGatewayHandler
→ 校验 Bearer Token（配置时）
→ 校验 Idempotency-Key / X-Notification-Id
→ 按 event_type 渲染飞书消息或卡片
→ FeishuClient 主动发送
→ 返回 2xx
```

通知网关不得再次调用采购状态流转接口。后端收到任意 2xx 才将通知视为发送成功；网络异常或非 2xx 由后端 Outbox 重试。

---

## 5. 正式角色和状态

### 5.1 角色

代码和接口中统一使用：

```text
APPLICANT
BUILDING_MANAGER
PURCHASER
WAREHOUSE_MANAGER
ADMIN
```

禁止创建以下平行角色编码：

```text
REQUESTER
REVIEWER
WAREHOUSE
```

### 5.2 正式采购状态

统一使用后端状态：

```text
DRAFT
PENDING_REVIEW
REJECTED
PENDING_PURCHASE
PURCHASING
PENDING_WAREHOUSE
COMPLETED
```

不要新增以下正式状态：

```text
READY_TO_SUBMIT
REVIEW_FILLING
READY_FOR_PURCHASER
PURCHASER_FILLING
READY_FOR_WAREHOUSE
```

卡片可以存在页面视图状态，但不能将视图状态当成采购业务状态。

---

## 6. 后端接口通用规则

基础路径：

```text
/api/v1
```

除健康检查外，采购后端请求必须携带可信网关身份头：

```text
X-Platform-Type: FEISHU
X-Platform-User-Id: <feishu open_id>
X-Gateway-Timestamp: <Unix 秒级时间戳>
X-Gateway-Nonce: <16 至 128 位随机数>
X-Gateway-Signature: <HMAC-SHA256 十六进制摘要>
X-Request-Id: <trace id，可选>
```

签名原文严格依次为：

```text
HTTP_METHOD
URL_PATH
PLATFORM_TYPE
PLATFORM_USER_ID
TIMESTAMP
NONCE
```

字段以换行符连接。`URL_PATH` 不包含查询字符串。共享密钥使用 `IDENTITY_GATEWAY_SECRET`，只能存在于安全配置。默认签名有效窗口为 300 秒；每个请求使用新 nonce。开发环境可以使用 `TEST_PLATFORM`，生产环境禁止。

请求体中禁止传入：

- `operator_employee_id`
- `operator_open_id`
- `roles`
- 当前操作者姓名
- 当前操作者楼宇权限

数据规则：

- 时间使用 ISO 8601；
- 日期使用 `YYYY-MM-DD`；
- 金额使用字符串；
- 数量使用字符串；
- 税率使用百分数值字符串；
- Python 内部计算使用 `Decimal`；
- 禁止 float。

所有修改采购单字段的接口必须携带：

```text
expected_version
```

所有正式确定性操作必须携带：

```text
action_token
```

同一次用户动作重试必须复用相同 token。

---

## 7. 智能助手意图

首版只实现以下意图：

```python
class AssistantIntent(StrEnum):
    SEARCH_RECORDS = "SEARCH_RECORDS"
    PREFILL_REQUIREMENT = "PREFILL_REQUIREMENT"
    QUERY_STATUS = "QUERY_STATUS"
    PROCESS_GUIDE = "PROCESS_GUIDE"
    SUMMARIZE_RESULTS = "SUMMARIZE_RESULTS"
    SEARCH_CATALOG = "SEARCH_CATALOG"
    CARD_HELP = "CARD_HELP"
```

模型必须输出 Pydantic 强类型对象，禁止输出自由格式 HTTP 请求。

建议模型：

```python
class RequirementReference(BaseModel):
    requirement_id: int | None = None
    requirement_no: str | None = None


class PurchaseSearchFilters(BaseModel):
    requirement_no: str | None = None
    supplier_id: int | None = None
    status: str | None = None
    device_name: str | None = None
    brand: str | None = None
    model: str | None = None
    created_from: date | None = None
    created_to: date | None = None


class ApplicantPrefillFields(BaseModel):
    device_profession: str | None = None
    device_name: str | None = None
    brand: str | None = None
    model: str | None = None
    quantity: str | None = None
    unit: str | None = None
    application_reason: str | None = None
    applicant_remark: str | None = None


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: AssistantIntent
    requirement: RequirementReference | None = None
    search_filters: PurchaseSearchFilters | None = None
    prefill_fields: ApplicantPrefillFields | None = None
    catalog_query: str | None = None
    guide_topic: str | None = None
    user_question: str | None = None
```

模型不得输出：

- 操作人 ID；
- 角色；
- 正式状态；
- `expected_version`；
- `action_token`；
- 任意处理人 ID；
- 未经后端返回的供应商 ID；
- 业务事实数字。

---

## 8. 统一的“问智能助手”交互

### 8.1 所在窗口

卡片中的“问智能助手”按钮不在卡片内部打开聊天框。

点击后仍在当前飞书机器人私聊窗口继续聊天。

调用链：

```text
用户点击“问智能助手”
→ 卡片回调
→ 后端创建或恢复 Agent 会话
→ Redis 写入当前卡片帮助上下文
→ 机器人在当前私聊窗口发送提示
→ 用户继续发送文本问题
```

### 8.2 Redis 卡片上下文

示例：

```json
{
  "purchase_request_id": 101,
  "current_action": "CARD_HELP",
  "active_card_type": "BUILDING_MANAGER_FORM",
  "focused_role": "BUILDING_MANAGER",
  "focused_field": "contract_type",
  "last_seen_backend_version": 6,
  "awaiting_confirmation": false,
  "last_recommendations": []
}
```

`last_seen_backend_version` 只能用于展示和冲突提示。真正保存字段前必须重新获取后端最新详情。

### 8.3 Agent 回答类型

Agent 可以返回三种结果。

#### 纯解释

例如：

```text
合同类型仅在“是否需要合同”为“是”时必填。
```

#### 查询结果

例如历史供应商、历史价格、采购状态。

#### 预填建议卡片

例如：

```text
预填建议

供应商：北京信达科技有限公司
付款方式：对公转账
合同类型：采购合同

[应用到当前卡片]
[仅供参考]
```

点击“应用到当前卡片”后：

```text
重新读取后端详情和 version
→ 调用对应 PATCH 接口
→ 使用后端正式响应刷新业务卡片
```

Agent 不能直接执行正式提交动作。

---

## 9. 需求人完整交互

需求人支持两种入口：

- 自然语言快速创建；
- 结构化卡片直接填写。

两种入口必须复用同一后端草稿和同一张正式卡片。

### 9.1 需求人自然语言创建

示例：

```text
我要申请 5 块 2TB 的服务器硬盘，用于故障替换。
```

Agent 提取候选：

```json
{
  "device_name": "服务器硬盘",
  "model": "2TB",
  "quantity": "5",
  "unit": "块",
  "application_reason": "故障替换"
}
```

处理流程：

```text
POST /requirements 创建 DRAFT
→ PATCH /requirements/{id}/applicant-fields
→ 后端返回正式字段、missing_fields、next_missing_field 和 version
→ 根据后端 next_missing_field 追问
```

### 9.2 一次追问一个字段

追问顺序不由 Agent 固定写死，必须使用后端返回的：

```text
next_missing_field
```

后端 V1.5 / 数据库 V1.4 当前提交前必填字段为：

```text
device_profession
device_name
quantity
unit
application_reason
```

`brand` 和 `model` 当前为可选字段。Agent 可以主动询问并推荐品牌、型号作为信息完善，但不得因为品牌或型号为空阻止提交；若业务仍要求二者必填，必须先修改后端契约。

当用户希望补充型号，Agent 可以调用：

```http
GET /api/v1/recommendations/products
```

并最多展示 3 个候选：

```text
请问您需要的具体设备型号是什么？

根据历史采购记录，为您找到：

1. 华为 S5735-L24T4S-A1
2. 华为 S5735S-L24T4S-A
3. 华为 S1730S-L24T-A1

您可以回复序号，也可以直接输入型号。
```

最近候选只在 Redis 保存稳定引用。

用户回复“第一个”时：

```text
读取 Redis 引用
→ 重新调用后端查询或校验
→ PATCH applicant-fields
→ 根据后端响应继续
```

### 9.3 需求人草稿卡片

```text
新建采购申请                         草稿

所属楼宇：一号楼
设备专业：服务器存储
设备名称：服务器硬盘
品牌：希捷
型号：Exos 2TB
数量：5
单位：块
需求原因：故障替换
备注：无

当前缺少：无

[保存草稿]
[提交审批]
[问智能助手]
[取消]
```

保存调用：

```http
PATCH /api/v1/requirements/{id}/applicant-fields
```

### 9.4 提交审批确认卡片

```text
提交采购审批确认

采购单编号：PR-202607-0001
所属楼宇：一号楼

设备专业：服务器存储
设备名称：服务器硬盘
品牌：希捷
型号：Exos 2TB
数量：5 块
需求原因：故障替换

审批楼长：李四

[确认提交审批]
[返回修改]
[问智能助手]
```

正式提交：

```http
POST /api/v1/requirements/{id}/submit-review
```

成功后：

- 状态为 `PENDING_REVIEW`；
- 更新需求人原卡片；
- 向楼长推送待审核卡片；
- Agent 会话可保存快照并结束当前创建动作。

---

## 10. 楼长完整交互

楼长以卡片为主，Agent 为辅助。

### 10.1 待审核卡片

```text
待审核采购申请

采购单编号：PR-202607-0001
需求人：张三
所属楼宇：一号楼

设备专业：服务器存储
设备名称：服务器硬盘
品牌：希捷
型号：Exos 2TB
数量：5 块
需求原因：故障替换

当前状态：待楼长审核

[填写审核信息]
[驳回]
[问智能助手]
```

权限由后端同时校验：

- 当前用户具有 `BUILDING_MANAGER`；
- 采购单楼宇属于该楼长有效楼宇；
- 当前处理人合法。

### 10.2 楼长审核信息卡片

字段以正式后端接口为准：

```text
楼长审核信息

拟定供应商：[选择]
供应商联系人姓名：[输入]
供应商联系方式：[输入]
供应商链接：[输入]
预计单价：[输入]
预计总价：[后端计算结果，只读展示]
是否需要合同：[是/否]
合同类型：[条件必填]
付款方式：[输入或选择]
预计到货日期：[日期]
质保信息：[输入]
楼长备注：[选填]

[保存]
[提交采购员]
[查询历史采购]
[问智能助手]
```

保存接口：

```http
PATCH /api/v1/requirements/{id}/review-fields
```

后端返回：

- `version`
- `missing_fields`
- `fields_complete`

字段名统一采用：

```text
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

预计总价由后端根据申请数量和预计单价计算并校验。卡片不得自行把前端计算结果当作权威值。

当前审核轮次第一次保存楼长字段时，后端创建 `review_status=DRAFT` 的 `purchase_review`；后续保存更新同一条记录。通过或驳回时在同一事务中把该记录更新为 `COMPLETED`。重新提交后才创建新的审核轮次。

### 10.3 楼长向 Agent 提问

可问：

- 这款设备以前由哪些供应商供货？
- 这家供应商是否在黑名单？
- 上次采购价格是多少？
- 合同类型怎么填？
- 付款方式一般是什么？
- 质保通常几年？

数据查询使用：

```http
GET /api/v1/recommendations/purchase-history
GET /api/v1/recommendations/suppliers
GET /api/v1/suppliers
GET /api/v1/suppliers/{supplier_id}
```

Agent 最多展示 3 个候选。

### 10.4 楼长提交采购员确认卡片

```text
楼长审核确认

采购单：PR-202607-0001

需求信息
设备：希捷 Exos 2TB 服务器硬盘
数量：5 块
原因：故障替换

楼长补充
拟定供应商：北京信达科技有限公司
联系方式：400-xxx
预计单价：人民币 5,800.00 元
预计总价：人民币 29,000.00 元
需要合同：是
合同类型：采购合同
付款方式：对公转账
预计到货：2026-08-10
质保：三年

下一处理人：王五

[确认提交采购员]
[返回修改]
[问智能助手]
```

正式提交：

```http
POST /api/v1/requirements/{id}/submit-purchaser
```

成功后：

- 状态为 `PENDING_PURCHASE`；
- 后端将当前轮次的 DRAFT 审核记录更新为 COMPLETED/APPROVED，不重复新增同轮记录；
- 更新楼长原卡片；
- 后端事务写入通知 Outbox，由通知网关异步向采购员推送卡片。

### 10.5 楼长驳回

```text
驳回采购申请

采购单：PR-202607-0001
驳回原因：[必填]

[确认驳回]
[取消]
[问智能助手]
```

接口：

```http
POST /api/v1/requirements/{id}/reject
```

成功后：

- 状态为 `REJECTED`；
- 当前处理人回到需求人；
- 不新建采购单；
- 当前轮次审核记录更新为 COMPLETED/REJECTED；此前未保存楼长字段时，后端在同一事务中创建并完成该轮记录；
- 后端写入通知 Outbox，由通知网关异步通知需求人。

### 10.6 供应商黑名单

楼长可以在对话中说：

```text
把采购单 PR-202607-0001 的供应商加入黑名单，原因是连续延期。
```

Agent 只负责：

- 定位采购单；
- 查询其关联供应商；
- 收集黑名单类型；
- 收集原因；
- 收集持续类型和期限；
- 生成确认卡片。

确认卡片：

```text
确认加入供应商黑名单

供应商：北京信达科技有限公司
来源采购单：PR-202607-0001
黑名单类型：交付延期
原因：连续两次延期交付
持续类型：有限期限
开始：2026-08-10
结束：2027-02-10

[确认拉黑]
[返回修改]
```

接口：

```http
POST /api/v1/suppliers/{supplier_id}/blacklist
```

限制：

- 仅 `BUILDING_MANAGER` 可以登记；
- `requirement_id` 必须对应已经 `COMPLETED` 的采购申请；
- 禁止根据模糊名称直接执行拉黑；
- `PERMANENT` 时 `end_at` 必须为空；
- `LIMITED` 时 `end_at` 必填；
- 提前解除只允许原登记楼长或 `ADMIN`，且解除原因必填。

---

## 11. 采购员完整交互

### 11.1 待采购卡片

```text
待采购任务

采购单：PR-202607-0001
需求人：张三
楼长：李四

设备：希捷 Exos 2TB 服务器硬盘
数量：5 块
楼长拟定供应商：北京信达科技有限公司
预计总价：人民币 29,000.00 元
预计到货：2026-08-10
质保：三年

[开始采购填写]
[查看完整记录]
[问智能助手]
```

开始采购可调用：

```http
POST /api/v1/requirements/{id}/start-purchase
```

### 11.2 采购员填写卡片

```text
采购执行信息

正式供应商：[选择或新增]
供应商税号：[输入]
开户行：[输入]
银行账号：[输入]
注册地址：[输入]
合同联系方式：[输入]
实际单价：[输入]
实际总价：[后端计算结果，只读展示]
项目税率：[输入]
采购时间：[日期时间]
采购备注：[选填]
同步更新供应商档案：[明确勾选，默认否]

[保存]
[提交仓库]
[查询供应商资料]
[问智能助手]
```

保存接口：

```http
PATCH /api/v1/requirements/{id}/purchase-fields
```

字段名包含：

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

实际总价由后端根据申请数量和实际单价计算并校验。本次采购始终保存供应商资料快照；只有采购员明确确认且 `update_supplier_profile=true` 时，后端才同步更新供应商当前可复用档案。

Agent 可以帮助查询供应商资料，但必须尊重后端敏感字段裁剪。

### 11.3 采购员询问 Agent

示例：

```text
帮我查北京信达科技有限公司的税号和开户行。
```

Agent：

```text
搜索供应商候选
→ 用户或上下文确定 supplier_id
→ 获取供应商详情
→ 返回后端允许展示的数据
→ 可生成预填建议卡片
```

禁止只根据名称模糊匹配后直接写入正式供应商。

### 11.4 提交仓库确认卡片

```text
采购提交确认

采购单：PR-202607-0001
正式供应商：北京信达科技有限公司
税号：9111...
开户行：中国工商银行
银行账号：6222****1234
注册地址：北京市……
合同联系方式：400-xxx
实际总价：人民币 28,000.00 元
税率：13.00%
采购时间：2026-08-03

下一处理人：赵六

[确认提交仓库]
[返回修改]
[问智能助手]
```

接口：

```http
POST /api/v1/requirements/{id}/submit-warehouse
```

成功后：

- 状态为 `PENDING_WAREHOUSE`；
- 更新采购员原卡片；
- 后端事务写入通知 Outbox，由通知网关异步向仓库管理员推送卡片。

---

## 12. 仓库管理员完整交互

### 12.1 待入库卡片

```text
采购待入库

采购单：PR-202607-0001
设备：希捷 Exos 2TB 服务器硬盘
采购数量：5 块
供应商：北京信达科技有限公司
采购员：王五
实际总价：人民币 28,000.00 元

仓库位置：[输入]
实际入库数量：[默认采购数量，可修改]
入库备注：[条件必填]

[保存入库信息]
[确认入库]
[问智能助手]
```

保存接口：

```http
PATCH /api/v1/requirements/{id}/warehouse-fields
```

字段名统一采用：

```text
warehouse_location
received_quantity
receipt_remark
```

当前仍是一次性入库，不支持分批入库；`received_quantity` 可以小于、等于或大于申请数量。少于申请数量时，`receipt_remark` 必填。

### 12.2 Agent 辅助

仓库管理员可以问：

- 当前采购数量是多少？
- 采购单由谁发起？
- 同类设备历史入库位置是什么？

只有后端提供相应查询能力时才能回答。没有接口时明确说明暂不支持，不能生成虚假库位。

### 12.3 确认入库卡片

```text
确认完成入库

采购单：PR-202607-0001
仓库位置：A 区 3 号库位
入库数量：5 块
备注：外包装完好

确认后采购流程将结束。

[确认入库]
[返回修改]
```

正式接口：

```http
POST /api/v1/requirements/{id}/complete
```

成功后：

- 状态为 `COMPLETED`；
- 当前处理人为空；
- 更新当前仓库卡片；
- 后端事务为需求人、楼长和采购员写入通知 Outbox，由通知网关异步发送完成通知。

---

## 13. 卡片清单

第一版至少实现：

1. 采购中心首页卡片；
2. 需求人采购草稿卡片；
3. 需求人提交确认卡片；
4. 楼长待审核卡片；
5. 楼长审核信息卡片；
6. 楼长提交采购员确认卡片；
7. 驳回确认卡片；
8. 供应商黑名单确认卡片；
9. 采购员待采购卡片；
10. 采购员采购执行卡片；
11. 采购员提交仓库确认卡片；
12. 仓库待入库卡片；
13. 入库确认卡片；
14. 完成结果卡片；
15. 通用 Agent 预填建议卡片；
16. 通用查询结果卡片。

---

## 14. BackendClient Port

应用层只依赖强类型 `BackendClient`。

至少定义：

```python
class BackendClient(Protocol):
    async def get_current_user(...) -> CurrentUser: ...

    async def create_requirement(...) -> RequirementSummary: ...
    async def update_applicant_fields(...) -> RequirementDetail: ...
    async def get_requirement(...) -> RequirementDetail: ...
    async def list_requirements(...) -> RequirementPage: ...
    async def list_handler_candidates(...) -> HandlerCandidates: ...
    async def submit_review(...) -> RequirementDetail: ...
    async def resubmit_review(...) -> RequirementDetail: ...

    async def update_review_fields(...) -> RequirementDetail: ...
    async def reject_requirement(...) -> RequirementDetail: ...
    async def submit_purchaser(...) -> RequirementDetail: ...

    async def start_purchase(...) -> RequirementDetail: ...
    async def update_purchase_fields(...) -> RequirementDetail: ...
    async def submit_warehouse(...) -> RequirementDetail: ...

    async def update_warehouse_fields(...) -> RequirementDetail: ...
    async def complete_requirement(...) -> RequirementDetail: ...

    async def search_suppliers(...) -> SupplierPage: ...
    async def get_supplier(...) -> SupplierDetail: ...
    async def create_or_update_supplier(...) -> SupplierSummary: ...
    async def blacklist_supplier(...) -> SupplierBlacklistResult: ...
    async def release_supplier_blacklist(...) -> SupplierBlacklistResult: ...

    async def recommend_products(...) -> ProductRecommendations: ...
    async def recommend_purchase_history(...) -> PurchaseHistoryRecommendations: ...
    async def recommend_suppliers(...) -> SupplierRecommendations: ...
    async def search_purchase_records(...) -> PurchaseRecordPage: ...
    async def get_requirement_timeline(...) -> RequirementTimeline: ...

    async def get_or_create_agent_conversation(...) -> AgentConversation: ...
    async def append_agent_message(...) -> AgentMessage: ...
    async def get_agent_state(...) -> AgentSessionState: ...
    async def update_agent_state(...) -> AgentSessionStateSaveResult: ...
    async def snapshot_agent_state(...) -> AgentSessionSnapshot: ...
    async def complete_agent_conversation(...) -> AgentConversationCompletion: ...
```

---

## 15. Agent 会话接口

使用后端提供的接口：

```http
POST /api/v1/agent/conversations/active
POST /api/v1/agent/conversations/{conversation_id}/messages
GET  /api/v1/agent/conversations/{conversation_id}/messages
GET  /api/v1/agent/conversations/{conversation_id}/state
PUT  /api/v1/agent/conversations/{conversation_id}/state
POST /api/v1/agent/conversations/{conversation_id}/snapshot
POST /api/v1/agent/conversations/{conversation_id}/complete
```

规则：

- 同一员工同一 `current_action` 默认只有一条活动会话；
- `external_message_id` 在同一会话内唯一，消息接口返回 `duplicate` 用于幂等识别；
- GET messages 按 `page`、`page_size` 分页，默认 50、最大 200，按 `created_at` 和 `message_id` 正序；
- 不保存或返回模型内部思维过程；
- Redis Key 为 `agent:session:{conversation_id}`，由后端管理；
- 读取和更新成功后刷新 TTL；
- 默认 TTL 为 72 小时；
- Redis Key 不存在时，后端从 MySQL 最新快照恢复并回写 Redis；没有可恢复快照时返回 `SESSION_EXPIRED`；
- Redis 状态更新不修改正式业务表；
- 正式字段必须调用采购业务接口；
- 关键确认、正式提交和异常中断时保存快照；
- 会话完成后保存最终快照并清理 Redis。

### 15.1 对现有会话结构的调整

后端文档示例中包含：

```text
collected_data
missing_fields
pending_field
awaiting_confirmation
```

在本项目最新架构中：

- `collected_data` 只能作为尚未写入后端的自然语言候选；
- 调用正式字段 PATCH 成功后，应以后端详情为准；
- `missing_fields` 和 `pending_field` 应优先使用后端响应；
- Redis 中可以缓存它们用于续聊，但不能作为最终业务校验；
- `awaiting_confirmation` 只表示 Agent 是否等待用户确认建议，不等于正式动作已经允许。

---

## 16. 推荐项目目录

```text
procurement-workflow-assistant/
├── pyproject.toml
├── README.md
├── AGENTS.md
├── .env.example
├── .gitignore
├── docs/
│   ├── architecture.md
│   ├── card-agent-interaction.md
│   ├── backend-contract.md
│   ├── assistant-session.md
│   ├── development-roadmap.md
│   ├── testing-strategy.md
│   └── open-decisions.md
├── src/
│   └── procurement_platform/
│       ├── bootstrap/
│       │   ├── settings.py
│       │   └── container.py
│       ├── domain/
│       │   ├── identity.py
│       │   ├── requirement.py
│       │   ├── supplier.py
│       │   ├── action.py
│       │   ├── card.py
│       │   ├── assistant.py
│       │   └── errors.py
│       ├── ports/
│       │   ├── backend_client.py
│       │   ├── llm_client.py
│       │   ├── channel.py
│       │   └── notification_delivery_store.py
│       ├── application/
│       │   ├── assistant/
│       │   │   ├── orchestrator.py
│       │   │   ├── intent_extractor.py
│       │   │   ├── query_service.py
│       │   │   ├── prefill_service.py
│       │   │   ├── guide_service.py
│       │   │   └── summary_service.py
│       │   ├── cards/
│       │   │   ├── applicant_service.py
│       │   │   ├── reviewer_service.py
│       │   │   ├── purchaser_service.py
│       │   │   └── warehouse_service.py
│       │   ├── actions/
│       │   │   └── router.py
│       │   └── notifications/
│       │       ├── gateway_service.py
│       │       └── renderer_registry.py
│       ├── adapters/
│       │   ├── backend/
│       │   │   ├── http_client.py
│       │   │   ├── dto.py
│       │   │   └── error_mapping.py
│       │   ├── llm/
│       │   │   └── openai_compatible.py
│       │   └── feishu/
│       │       ├── client.py
│       │       ├── event_adapter.py
│       │       ├── message_handler.py
│       │       ├── card_handler.py
│       │       ├── renderer.py
│       │       └── security.py
│       └── interfaces/http/
│           ├── app.py
│           ├── feishu_webhook.py
│           ├── notification_gateway.py
│           └── health.py
└── tests/
    ├── unit/
    ├── integration/
    └── contract/
```

---

## 17. 开发顺序

### 阶段 1：项目骨架与 BackendClient

完成：

- Settings；
- Domain DTO；
- BackendClient Protocol；
- FakeBackendClient；
- HttpBackendClient；
- 统一错误；
- 身份头；
- 契约测试；
- Health endpoint。

暂不实现 LLM。

### 阶段 2：飞书基础设施、身份签名与通知网关

完成：

- 飞书 Webhook；
- 验签和解密；
- 文本消息适配；
- 卡片回调；
- 回复、更新和主动推送；
- 采购后端 HMAC 身份签名器；
- 通知网关 HTTP 入口；
- `Authorization`、`Idempotency-Key`、`X-Notification-Id` 校验；
- 通知 event_type 渲染注册表；
- FakeFeishuClient；
- 飞书事件去重和通知投递幂等。

### 阶段 3：需求人卡片主流程

完成：

```text
/users/me
→ 创建草稿
→ 保存需求人字段
→ 获取后端完整性
→ 楼长候选
→ 提交审核
→ 后端写入通知 Outbox
→ 通知网关异步推送楼长
```

关闭 LLM 时必须可以运行。

### 阶段 4：智能助手需求人能力

完成：

- Agent 会话；
- 自然语言提取；
- 后端草稿预填；
- 一次追问一个字段；
- 产品推荐；
- 问智能助手；
- 预填建议卡片。

### 阶段 5：楼长卡片与 Agent 辅助

完成：

- 待审核卡片；
- 楼长字段；
- 历史采购推荐；
- 供应商推荐；
- 提交采购员；
- 驳回；
- 黑名单；
- 问智能助手。

### 阶段 6：采购员卡片与 Agent 辅助

完成：

- 待采购卡片；
- 供应商资料查询；
- 财务字段预填；
- 保存采购字段；
- 提交仓库；
- 问智能助手。

### 阶段 7：仓库流程

完成：

- 待入库卡片；
- 入库字段；
- Agent 查询辅助；
- 确认入库；
- 完成通知。

### 阶段 8：可靠性

完成：

- 通知幂等；
- 通知重试；
- 超时；
- 限流；
- trace id；
- 敏感字段脱敏；
- Agent 会话恢复；
- 日志和监控。

---

## 18. 测试要求

### 18.1 架构测试

必须证明：

```text
LLMClient 不可用
→ 四角色正式卡片流程仍可运行
```

```text
Agent Redis 状态丢失
→ 正式采购字段和状态不丢失
```

```text
后端正式动作成功、飞书通知失败
→ 不重复执行正式业务动作
```

### 18.2 BackendClient 契约测试

每个接口测试：

- 方法；
- 路径；
- 平台身份头；
- 网关时间戳、nonce 和 HMAC 签名；
- 签名原文不包含查询字符串；
- 每次请求使用新 nonce；
- JSON 或 Query；
- 金额字符串；
- 数量字符串；
- 成功解析；
- 业务错误；
- 超时；
- 非 JSON；
- 缺失字段；
- 未知枚举。

### 18.3 Agent 测试

覆盖：

- 强类型意图；
- 拒绝额外字段；
- 一次追问一个后端缺失字段；
- 最多展示 3 个推荐；
- “第一个”映射到 Redis 稳定引用；
- 正式写入前重新校验；
- Agent 不生成正式 action token；
- Agent 不执行正式提交；
- 数字来自后端；
- LLM 失败降级到卡片。

### 18.4 通知网关测试

覆盖：

- 可选 Bearer Token；
- 缺失或错误 Token；
- `Idempotency-Key`；
- `X-Notification-Id`；
- 相同 dedup_key 重复投递只发送一次；
- 任意 2xx 表示成功；
- 飞书超时或非成功结果返回非 2xx，供后端 Outbox 重试；
- 通知网关不调用正式业务状态接口；
- 未知 event_type 拒绝；
- payload 不包含足够渲染信息时拒绝；
- 不在日志输出令牌和敏感 payload。

### 18.5 卡片测试

覆盖：

- 卡片值来自后端；
- 正确携带版本；
- 正式动作生成 action token；
- 不信任卡片中的操作人；
- 不信任卡片中的角色和状态；
- 版本冲突刷新卡片；
- 重复点击幂等；
- 问智能助手建立上下文；
- 应用预填建议时重新加载最新版本。

### 18.6 权限与安全

覆盖：

- 楼长跨楼宇访问拒绝；
- 非当前处理人拒绝；
- 非采购员无法获取完整财务信息；
- 卡片伪造处理人 ID 被后端拒绝；
- Agent 无法扩大数据范围；
- 日志不包含完整银行账号和密钥。

---

## 19. 质量检查

每个任务完成前运行：

```bash
ruff format .
ruff format --check .
ruff check .
mypy src
pytest -q
git diff --check
git status --short
```

禁止：

- 删除关键测试；
- 降低 mypy strict；
- 大量使用 `Any`；
- 无说明的 `type: ignore`；
- 直接访问 MySQL；
- 在卡片 Handler 中调用 LLM；
- 在 Agent Session 中保存权威业务事实；
- 自行计算后端未返回的统计数字；
- 信任卡片或模型提供的身份、角色、状态和处理人；
- 通知失败后重做正式业务动作。

---

## 20. V1.5 已冻结的字段与剩余待确认项

### 20.1 已按 V1.5 / V1.4 冻结

以下字段不再作为待确认项：

```text
supplier_contact_name
supplier_contact_info
supplier_link
estimated_unit_price
estimated_total_price
expected_arrival_date
warranty_info
actual_unit_price
actual_total_price
received_quantity
receipt_remark
update_supplier_profile
```

总价由后端根据数量和单价计算并校验。卡片仅把后端结果作为权威展示。

### 20.2 仍需确认：通知入口 URL

联调说明定义后端配置 `NOTIFICATION_GATEWAY_URL`，但没有冻结本项目接收通知的具体 URL 路径。实现前需双方确定，例如 `/internal/notifications`，Codex 不得自行固化未确认路径。

### 20.3 仍需确认：通知事件模板

需要冻结：

- 所有 `event_type` 枚举；
- 每种事件 payload Schema；
- 对应飞书文本或卡片模板；
- 是否需要回传飞书 message_id；
- 网关错误响应结构。

### 20.4 仍需确认：通知幂等持久化

通知网关必须按 `Idempotency-Key` 幂等，但联调文档没有指定本项目的生产级去重存储。外部 Agent 又不得直接访问后端 MySQL/Redis。

开发前需确定：

- 是否允许本项目使用独立 Redis；
- 是否新增后端通知确认/查询接口；
- 是否由飞书发送接口提供可靠幂等键；
- 开发环境可否先使用内存 Store。

生产实现不能只使用进程内内存去重。

### 20.5 文档内部冲突：由谁主动发送通知

后端 V1.5 流程接口示例仍保留 `current_handler.platform_identities` 并写有“Agent 侧发送提醒”，但同一版本的 Outbox 章节和联调说明明确由后端后台任务调用通知网关异步发送。

为避免重复通知，本项目暂按以下原则设计：

```text
正式跨角色通知只响应后端 Outbox 网关调用
业务接口响应中的 platform_identities 不触发第二次发送
```

该原则需要后端负责人最终确认。

### 20.6 需求人品牌与型号

数据库 V1.4 将 `brand`、`model` 定义为可选，后端完整性以其返回的 `missing_fields` 为准。此前业务描述要求品牌和型号必填，两者存在业务要求差异。

当前 Codex 规范按后端权威原则处理：

- 不阻止品牌或型号为空的提交；
- Agent 可以主动推荐和补充；
- 如业务确实要求必填，应先调整后端字段完整性规则。

### 20.7 统计接口

当前 `/purchase-records` 返回明细，时间线接口返回关键流转；“次数、价格区间、主要供应商”等统计仍缺少正式统计接口。

确认前，LLM不得自行统计。

---

## 21. Codex 工作规则

开始每项任务前：

```bash
git status
git branch --show-current
git log -5 --oneline
```

然后：

1. 阅读 `AGENTS.md`；
2. 阅读与任务相关的 docs；
3. 检查工作区；
4. 创建功能分支；
5. 先补测试；
6. 不修改远程资源；
7. 除非明确要求，不提交、不推送、不创建 PR；
8. 遇到接口缺失或业务冲突，停止猜测并记录待确认项。

每次完成后汇报：

1. 开发前状态；
2. 实现范围；
3. 新增、修改和删除文件；
4. 调用链；
5. 使用的后端接口；
6. 测试结果；
7. Git 状态；
8. 已知限制；
9. 待确认项。

---

## 22. 第一项开发任务

新仓库第一项任务为：

> 建立项目骨架、领域 DTO、BackendClient Protocol、FakeBackendClient、HttpBackendClient 基础实现、统一错误映射和契约测试。暂不实现 Agent 主循环和四角色业务流程。

第一项任务验收：

- 可以根据飞书 open_id 调用 `/api/v1/users/me`；
- 支持统一响应结构；
- 支持业务错误映射；
- 金额、数量和税率不使用 float；
- 应用层不依赖 httpx；
- 不直接访问数据库；
- `ruff`、`mypy`、`pytest` 全部通过。

---

## 当前实现进度补充

- Task 3：需求人无 LLM 正式卡片流程已完成；
- Task 4：楼长无 LLM 正式卡片流程已完成；
- Task 5：采购员无 LLM 正式卡片流程已完成，包括开始采购、供应商查询与创建、采购
  字段保存、供应商档案同步明确确认、仓库管理员选择和提交仓库。实际总价以后端返回为
  准，跨角色通知仅由后端 Outbox 驱动。
- Task 6：仓库管理员无 LLM 正式卡片流程已完成，包括待办与详情、仓库位置和实际入库
  数量保存、少收备注规则、一次性完成确认及 `COMPLETED/current_handler=null` 展示。
