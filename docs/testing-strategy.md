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
