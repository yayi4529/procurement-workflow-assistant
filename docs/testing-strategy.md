# 测试策略 V2.1

## 架构

- LLM 不可用，四角色卡片流程可用；
- Redis 会话丢失，后端可从快照恢复；
- 通知失败不回滚业务；
- 业务接口成功不触发本项目直接双发通知。

## HMAC 身份签名

- 签名字段顺序固定；
- 使用 URL path，不含 query；
- HMAC-SHA256 hex；
- timestamp 秒级；
- nonce 长度合法且每请求不同；
- 密钥不进入日志；
- TEST_PLATFORM 仅开发使用。

## BackendClient

验证方法、路径、头、Query、JSON、响应、错误、超时、未知枚举和 timeline。

## Agent 会话

- active 会话；
- POST/GET messages；
- external_message_id 幂等；
- duplicate；
- 分页顺序；
- state TTL；
- Redis 恢复；
- SESSION_EXPIRED；
- snapshot/complete。

## 通知网关

- Bearer Token；
- Idempotency-Key；
- X-Notification-Id；
- 重复 dedup_key 只发送一次；
- 2xx 成功；
- Feishu 失败返回非 2xx；
- 未知 event_type；
- payload 校验；
- 不调用正式业务接口。

Task 2 另覆盖 Challenge、私聊文本、群聊忽略、空文本、错误 Token、
`foundation.echo`、事件去重与失败重试、Interaction 严格模型与渲染、通知 SHA-256
指纹、投递幂等、自定义路由以及 Fake Channel 无网络链路。

## 字段规则

- brand/model 可选；
- 单价输入、总价以后端为准；
- review DRAFT/COMPLETED 同轮更新；
- update_supplier_profile 明确确认；
- received_quantity 可小于/等于/大于；
- 少收时 receipt_remark 必填；
- 黑名单仅 COMPLETED 采购单。
## Task 3 测试

新增严格 BackendClient 契约测试与 Fake 驱动的无 LLM 端到端测试，覆盖字符串数量、
显式 null、可选 brand/model、角色/楼宇、候选楼长、首次提交、重新提交、版本递增及
调用端点隔离。架构约束继续禁止应用层依赖 httpx、飞书 SDK、LLM、MySQL 或 Redis。
## Task 4 测试

覆盖审核字段部分更新、显式 null、字符串金额、后端总价、合同条件必填、0/1/多候选
分支、版本冲突、稳定 action token、重复点击、驳回和提交采购员；正式链路不写 Agent
会话且不直接发送跨角色通知。

## Task 5 测试

覆盖新增 HTTP 接口的方法、路径、Query、JSON 和签名传输链路；覆盖空供应商关键词、
供应商候选与详情、敏感账号 repr、字符串金额和税率、后端总价、档案同步默认否、
仓库管理员候选、`expected_version`、稳定 `action_token` 及从 PENDING_PURCHASE 到
PENDING_WAREHOUSE 的无 LLM 集成链路。

## Task 6 测试

覆盖 `warehouse-fields` 与 `complete` 的方法、路径和 JSON 契约；覆盖字符串 Decimal
数量、零/负数、等量、多收、少收无备注、少收补备注、部分更新、显式 null、字段完整性、
current_handler 清空和从 PENDING_WAREHOUSE 到 COMPLETED 的无 LLM 集成链路。

## Task 7 测试

- 显式解析 `PROCUREMENT_LLM_ENABLED=false`，无 OpenAI 配置时容器可构建；
- 同一 Fake 后端切换后端返回的四角色身份，覆盖驳回、原单重提和完整状态链；
- 断言正式 E2E 没有调用任一 Agent Session 接口；
- 架构测试禁止正式卡片应用模块导入 LLM、OpenAI 或 Agent Session；
- 通知网关不得依赖 `BackendClient` 或任何业务流转方法；
- Task 2～6 回归继续覆盖事件/通知去重、版本冲突、旧卡片刷新、权限和字段完整性。
