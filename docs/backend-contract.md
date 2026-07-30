# 后端接口契约摘要 V1.5

契约基线：后端接口 V1.5、数据库 V1.4、《后端接口联调说明》。

## 1. 基础与可信身份签名

基础路径：`/api/v1`。

除健康检查外，每个请求必须携带：

```text
X-Platform-Type
X-Platform-User-Id
X-Gateway-Timestamp
X-Gateway-Nonce
X-Gateway-Signature
X-Request-Id（可选）
```

签名原文为：

```text
HTTP_METHOD
URL_PATH
PLATFORM_TYPE
PLATFORM_USER_ID
TIMESTAMP
NONCE
```

使用换行符连接，URL_PATH 不包含查询字符串。使用 `IDENTITY_GATEWAY_SECRET` 计算 HMAC-SHA256 十六进制摘要。默认有效期 300 秒，每次请求使用新 nonce。

## 2. 数据规则

- 金额：字符串；
- 数量：字符串；
- 税率：百分数字符串；
- 日期：`YYYY-MM-DD`；
- 时间：ISO 8601；
- 修改：`expected_version`；
- 正式动作：`action_token`。

## 3. 核心业务接口

```text
GET   /users/me
GET   /requirements/{id}/handler-candidates
POST  /requirements
PATCH /requirements/{id}/applicant-fields
GET   /requirements/{id}
GET   /requirements
POST  /requirements/{id}/submit-review
POST  /requirements/{id}/resubmit-review
PATCH /requirements/{id}/review-fields
POST  /requirements/{id}/reject
POST  /requirements/{id}/submit-purchaser
POST  /requirements/{id}/start-purchase
PATCH /requirements/{id}/purchase-fields
POST  /requirements/{id}/submit-warehouse
PATCH /requirements/{id}/warehouse-fields
POST  /requirements/{id}/complete
```

## 4. 查询、推荐和时间线

```text
GET /purchase-records
GET /requirements/{id}/timeline
GET /suppliers
GET /suppliers/{supplier_id}
GET /recommendations/products
GET /recommendations/purchase-history
GET /recommendations/suppliers
```

后端自动按员工、角色和楼宇裁剪范围。

## 5. 已冻结字段

楼长：

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

采购员：

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

仓库：

```text
warehouse_location
received_quantity
receipt_remark
```

预计/实际总价由后端根据数量和单价计算并校验。

## 6. Agent 会话

```text
POST     /agent/conversations/active
POST/GET /agent/conversations/{conversation_id}/messages
GET/PUT  /agent/conversations/{conversation_id}/state
POST     /agent/conversations/{conversation_id}/snapshot
POST     /agent/conversations/{conversation_id}/complete
```

- Redis TTL 72 小时；
- Redis 丢失时从 MySQL 快照恢复；
- 无快照时返回 `SESSION_EXPIRED`；
- `external_message_id` 会话内唯一；
- 不保存或返回模型内部思维过程。

## 7. 通知 Outbox

正式业务事务写入 `notification_outbox`。后端 worker 调用平台无关通知网关，失败不回滚业务。

通知请求头：

```text
Authorization: Bearer <token>（配置时）
Idempotency-Key: <dedup_key>
X-Notification-Id: <notification_id>
```

通知网关必须幂等，任意 2xx 表示成功。

## 8. Task 1 客户端实现

调用链：

```text
Application
→ BackendClient
→ SignedBackendTransport
→ GatewayIdentitySigner
→ HTTP Backend
```

签名原文严格为大写方法、无查询字符串的 path、平台类型、平台用户 ID、Unix
秒级时间戳和新 nonce，以单个换行连接。签名为共享密钥计算的
HMAC-SHA256 小写十六进制摘要。共享密钥只通过
`PROCUREMENT_IDENTITY_GATEWAY_SECRET` 注入，不得写入日志。

Task 1 实现的接口：

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

客户端拒绝非 JSON、缺字段、额外字段、成功但无 data、未知稳定枚举以及未知错误码。
未知错误码映射为 `UnknownBackendError`，不会被当作成功。

## 9. Task 2 通知网关当前契约

接收路径由 `PROCUREMENT_NOTIFICATION_GATEWAY_PATH` 配置，开发默认值
`/internal/notifications` 不是已冻结的正式路径。

```text
POST <configured path>
Authorization: Bearer <configured token>
Idempotency-Key: <body.dedup_key>
X-Notification-Id: <body.notification_id>
```

Body 使用严格 `NotificationGatewayRequest`，当前仅接受 `platform_type=FEISHU`。
`event_type` 必须已注册；生产容器不注册测试事件或未经确认的业务事件。成功及相同的已
成功重复投递返回 204；Header 不一致为 400，鉴权失败为 401，幂等冲突为 409，未知
事件/非法 Payload 为 422，飞书失败/超时为 502/503。
