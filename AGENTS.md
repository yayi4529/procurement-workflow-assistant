AGENTS.md

本文件是 Codex 在 procurement-workflow-assistant 仓库中工作的最高级项目约束。

当前开发阶段：

将 Task 1～Task 7 的无 LLM 卡片流程，从 FakeBackendClient 切换到运行在 http://127.0.0.1:8001 的真实采购后端，并完成严格契约对齐。

1. 项目目标

卡片
→ 正式填写和确定性操作

Agent
→ 查询、解释、推荐、总结和候选预填

采购后端
→ 身份、角色、楼宇、字段、状态、处理人、版本、幂等、事务、审计和通知 Outbox

Agent 不是采购流程必经路径。

2. 当前联调环境

默认本地拓扑：

procurement-workflow-assistant
→ http://127.0.0.1:8000

Procurement-Agent backend
→ http://127.0.0.1:8001

Backend MySQL
→ 127.0.0.1:3307

Backend Redis
→ 127.0.0.1:6380

真实字段级契约：

http://127.0.0.1:8001/openapi.json

字段级请求和响应以运行时 OpenAPI 与真实响应为准。旧文档和 Fake 模型只能作为背景，不得覆盖真实 OpenAPI。

3. 开发前必须阅读

AGENTS.md
README.md
CODEX_PROJECT_SPEC.md
docs/architecture.md
docs/backend-contract.md
docs/backend-v1.5-delta.md
docs/testing-strategy.md
docs/open-decisions.md
docs/no-llm-e2e-acceptance.md
docs/feishu-fake-debugging.md

同时阅读后端仓库：

README.md
docs/本地开发环境搭建与启动指南.md
docs/后端接口联调说明.md
运行时 /openapi.json

不得只根据任务提示猜测 Schema。

4. Git 规则

开始前执行：

git status
git branch --show-current
git log -8 --oneline
git remote -v

要求：

不覆盖用户未提交修改；

工作区不干净时先报告；

不把后端仓库复制进本仓库；

两个仓库保持并列目录；

联调修改使用独立分支；

除非用户明确要求，不 commit；

不 push；

不创建 PR；

不修改远程资源；

禁止 git reset --hard、git clean -fd 和未经允许的 stash。

建议联调分支：

integration/backend-http-contract

如果用户已经指定其他分支，保留用户分支。

5. 正式流程不得依赖 LLM

以下操作不得经过 LLM：

保存需求人字段
提交楼长
重新提交
保存楼长字段
驳回
提交采购员
开始采购
保存采购字段
提交仓库
保存入库字段
确认完成
选择下一处理人
拉黑或解除黑名单

当前联调必须保持：

PROCUREMENT_LLM_ENABLED=false

不得为了联调引入 OpenAI SDK、Prompt、AssistantOrchestrator 或 Agent Session 调用。

6. 后端是唯一事实来源

只采用后端返回的：

当前用户
employee_id
角色
楼宇
正式字段
missing_fields
allowed_actions
status
current_handler
version
处理人候选
供应商
黑名单
统计数据

禁止：

从卡片 value 信任操作者身份
从客户端自行声明角色或楼宇
由客户端决定下一处理人是否合法
由客户端计算并覆盖正式总价
由 Redis 或本地内存替代后端正式数据

7. 数据访问边界

本项目只能通过 BackendClient HTTP Port 使用采购后端。

禁止：

直接访问后端 MySQL
直接访问后端 Redis
导入后端 ORM Model
导入后端 Repository
共享后端数据库连接
把后端 Secret 发给浏览器或飞书

真实飞书身份绑定应由后端种子脚本、后端管理员或明确的后端联调任务完成。本项目不得增加直连数据库的身份绑定实现。

8. HMAC 请求强制规则

所有 /api/v1/* 请求必须由：

GatewayIdentitySigner
→ SignedBackendTransport

添加：

X-Platform-Type
X-Platform-User-Id
X-Gateway-Timestamp
X-Gateway-Nonce
X-Gateway-Signature

签名原文：

HTTP_METHOD
URL_PATH
PLATFORM_TYPE
PLATFORM_USER_ID
TIMESTAMP
NONCE

强制要求：

Method 大写；

path 不包含 query；

platform type 大写；

nonce 每次请求唯一；

网络重试重新生成 timestamp、nonce 和 signature；

Secret 使用 SecretStr；

Secret 不得进入 repr、日志、异常或测试快照。

不得由 Router、Application Service 或卡片 Handler 自行拼签名。

9. 依赖方向

interfaces/adapters
→ application
→ domain/ports

禁止：

domain → FastAPI/httpx/lark_oapi
application → 具体飞书 SDK
card handler → LLM
application → 后端 DTO
domain → 后端 HTTP Envelope
HttpBackendClient → 业务流程决策

推荐结构：

Backend HTTP JSON
→ Backend DTO
→ Adapter Mapper
→ Domain Model
→ Application Service
→ InteractionView
→ Feishu Renderer

10. 真实 OpenAPI 工作流

每次开始契约联调：

New-Item -ItemType Directory -Force .local

Invoke-WebRequest `
  http://127.0.0.1:8001/openapi.json `
  -OutFile .local\backend-openapi-8001.json

.local/ 不提交 Git。

修改接口前：

定位 OpenAPI path；

阅读 requestBody；

阅读 success response；

阅读业务错误；

对照真实后端源码或响应样例；

新建或修改严格 Backend DTO；

编写显式 Mapper；

更新 HttpBackendClient；

编写 Contract Test；

执行最小真实 Smoke；

记录契约差异。

不得：

先改 Domain Model 迎合任意 JSON
把所有模型改成 extra="ignore"
使用 dict[str, Any] 贯穿业务层
捕获 ValidationError 后伪造成功

11. 当前已知契约差异

11.1 Current User

后端当前用户响应包含：

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

正确处理：

BackendCurrentUserDTO
→ 显式映射
→ CurrentUser Domain

不得因为后端增加字段而放宽所有 Domain Model。

11.2 Requirement List

后端列表项主要包含：

requirement_id
requirement_no
device_name
status
current_handler_name

不要假设列表项必返 version、完整 current_handler 或完整字段。用户打开或操作采购单时重新获取详情。

11.3 Requirement Detail

后端详情当前使用：

review_records
purchase_execution
warehouse_receipt

项目展示模型可能使用：

review_fields
review_record
purchase_fields
warehouse_fields

必须在 Adapter 中显式转换，不能让 Application 层理解后端原始结构。

11.4 Fields Save Result

后端字段保存响应主要包含：

requirement_id
status
version
missing_fields
next_missing_field
fields_complete

如果卡片保存后需要完整数据：

PATCH 保存
→ 解析 BackendFieldsSaveDTO
→ GET requirement detail
→ 映射 Domain
→ 重新渲染

不得要求 PATCH 响应返回其未定义的完整嵌套快照。

11.5 HTTP 模式确定性入口

检查 BaseMessageHandler 的 backend_client 注入。

真实 HTTP 模式下，开发命令：

采购测试

必须使用 HttpBackendClient 获取当前用户和角色入口，不得只在 BackendMode.FAKE 时注入 BackendClient。

开发提示语不得写成“当前 Fake 身份”，应使用与 Backend Mode 无关的文字。

12. 联调实现顺序

前一阶段未通过时不要跳到完整 E2E。

阶段 A：基础连接

/health
/ready
/openapi.json
Settings
backend_mode=http
HMAC Secret
timeout

阶段 B：当前用户

唯一首个业务接口：

GET /api/v1/users/me

必须确认：

HMAC 成功
FEISHU open_id 已绑定
Backend DTO 校验成功
Domain Mapper 成功
角色和楼宇正确

阶段 C：需求人

create_requirement
update_applicant_fields
get_requirement
list_handler_candidates(BUILDING_MANAGER)
submit_review
resubmit_review

阶段 D：楼长

list PENDING_FOR_ME
get_requirement
update_review_fields
reject
submit_purchaser

阶段 E：采购员

start_purchase
supplier search/detail/create
update_purchase_fields
submit_warehouse

阶段 F：仓库

update_warehouse_fields
complete

阶段 G：通知

业务状态完整通过后再联调：

notification_outbox
→ backend worker
→ notification gateway
→ Feishu

13. 身份联调规则

后端使用：

platform_type=FEISHU
platform_user_id=ou_xxxxx

解析员工。

建议测试映射：

90001 → APPLICANT
90002 → BUILDING_MANAGER，building_id=1
90003 → PURCHASER
90004 → WAREHOUSE_MANAGER

本项目可以通过开发命令：

调试身份

向当前用户显示自己的 open_id。

要求：

身份探针在用户尚未映射后端时可用；

只在 development/test 启用；

production 禁止；

普通日志中的 open_id 脱敏；

不把 open_id 当作 employee_id；

不在卡片 value 中携带或信任角色。

14. 卡片和状态规则

稳定角色：

APPLICANT
BUILDING_MANAGER
PURCHASER
WAREHOUSE_MANAGER
ADMIN

稳定状态：

DRAFT
PENDING_REVIEW
REJECTED
PENDING_PURCHASE
PURCHASING
PENDING_WAREHOUSE
COMPLETED

不得创建平行枚举。

卡片规则：

从后端最新详情渲染；

保存携带 expected_version；

正式动作携带稳定 action_token；

不信任卡片传入的角色、状态、处理人；

操作前必要时重新获取详情；

冲突后刷新，不自动覆盖；

金额、数量和税率在边界使用字符串或 Decimal 安全转换，不使用 float；

后端计算总价时采用后端值。

15. 错误处理

必须保留并传播：

HTTP status
backend code
backend message
trace_id

程序分支使用 code，不依赖中文 message。

重点错误：

BACKEND_UNAVAILABLE
BACKEND_TIMEOUT
BACKEND_NON_JSON
BACKEND_INVALID_ENVELOPE
BACKEND_INVALID_DATA
USER_NOT_FOUND
PERMISSION_DENIED
BUILDING_NOT_ALLOWED
INVALID_HANDLER
INVALID_STATUS
MISSING_REQUIRED_FIELDS
CONCURRENT_MODIFICATION
DUPLICATE_OPERATION

规则：

BACKEND_INVALID_DATA：修复 DTO，不吞错，不伪造成功；

CONCURRENT_MODIFICATION：重新 GET 详情，不覆盖；

DUPLICATE_OPERATION：使用同一 token 查询当前状态；

timeout：不得生成新 action_token 盲目重试同一正式动作。

16. 通知规则

跨角色通知只允许：

Backend notification_outbox
→ Backend Worker
→ Notification Gateway
→ RendererRegistry
→ FeishuChannelClient

禁止：

业务成功后直接向下一角色 send
通知失败后重做业务动作
绕过 Outbox 发送同一通知

正式通知 event_type 和 Payload 未完全冻结时：

不创造生产事件；

不把 DEV_NOTIFICATION_TEST 当成正式事件；

更新 docs/open-decisions.md；

业务联调通过各角色待办入口推进；

等后端确认后再注册正式 Renderer。

第一轮真实业务联调建议：

PROCUREMENT_NOTIFICATION_GATEWAY_ENABLED=false

17. 测试要求

每个真实接口适配变更必须包含：

DTO Test

真实 success sample
缺字段
多字段
非法枚举
金额和日期
nullable

Transport Contract Test

method
path
query
JSON body
HMAC headers
Envelope
trace_id
error mapping

Mapper Test

Backend DTO
→ Domain Model

Application Regression

Task 1～Task 7 测试继续通过。

Architecture Test

永久保证：

正式卡片模块不 import LLM
Application 不 import 后端 DTO
本项目不直连 MySQL/Redis
通知网关不调用业务状态流转
HTTP 模式不构建 FakeBackendClient

Real Smoke

只使用隔离 TEST 数据，并记录：

endpoint
platform user（日志脱敏）
HTTP status
code
trace_id
requirement_id
version
status
current_handler

不得编造真实 Smoke 结果。

18. 质量检查

完成前实际运行：

ruff format .
ruff format --check .
ruff check .
mypy src
pytest -q
git diff --check
git status --short

如果执行真实后端 Smoke，还需报告：

后端 HEAD
OpenAPI 获取时间
使用的测试角色
成功接口
失败接口
trace_id
未完成项

禁止：

删除旧测试
降低 mypy strict
大量 Any
无说明 type: ignore
编造执行结果

19. 日志与安全

允许记录：

request_id
trace_id
endpoint
method
status_code
backend code
requirement_id
old/new version
old/new status
duration_ms
masked open_id

禁止记录：

App Secret
Verification Token
Encrypt Key
IDENTITY_GATEWAY_SECRET
Notification Token
Authorization
tenant_access_token
完整银行账号
完整原始飞书 Payload
完整卡片表单

错误日志不得打印完整 Settings 对象。

20. 发现契约冲突时

执行：

停止猜测；

保存真实 OpenAPI；

提供最小响应样例；

对照后端源码；

在 Adapter 中解决可映射差异；

无法映射时更新 docs/open-decisions.md；

在最终报告中说明；

等待后端负责人确认。

禁止：

静默统一冲突字段
静默增加接口
静默修改业务状态
将客户端假设描述成后端事实

21. 本阶段明确不做

除非用户另行下达任务，不要：

接入 LLM
实现 Task 8～12
修改后端数据库
修改后端业务状态机
开发生产 Redis 幂等 Store
创建正式通知事件
接入飞书群聊采购
重构所有模块
自动推送远程分支

联调修复聚焦：

HTTP Backend 模式
真实 OpenAPI DTO
Mapper
四角色卡片调用链
错误处理
契约测试
真实 Smoke

22. Codex 最终汇报格式

1. 开发前状态

当前分支
基线提交
工作区状态
后端地址
后端 HEAD（可获取时）

2. OpenAPI 基线

获取地址
获取时间
保存路径
涉及接口

3. 契约差异

逐项列出：

旧模型
真实后端
适配方案
是否需后端确认

4. 实现结果

Backend DTO
Mapper
HttpBackendClient
Container
Message Handler
Application
Tests
Docs

5. 真实调用链

Feishu
→ Webhook
→ Application
→ HttpBackendClient
→ Backend 8001

6. 测试结果

给出实际命令和结果。

7. Smoke 结果

逐接口说明成功或失败，失败附 code 和 trace_id。

8. 安全、并发与幂等

身份来源
HMAC
expected_version
action_token
敏感日志

9. Git 状态

是否 commit
是否 push
是否 PR
是否修改远程资源
工作区状态

10. 待确认项

只列真实未冻结问题，不得猜测。
