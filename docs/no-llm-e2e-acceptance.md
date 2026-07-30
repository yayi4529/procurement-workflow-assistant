# Task 7 无 LLM E2E 验收

## 配置与边界

```text
PROCUREMENT_LLM_ENABLED=false
无 OpenAI API Key
无 AssistantOrchestrator
无 Agent Session 调用
无 MySQL/Redis 直连
```

正式字段与状态只采用后端响应；字段保存携带 `expected_version`，正式动作携带稳定
`action_token`。业务响应不直接触发跨角色通知。

## 自动化角色与数据

| 角色 | 测试 employee_id | 楼宇 |
|---|---:|---|
| APPLICANT | 1 | 一号楼 |
| BUILDING_MANAGER | 7 | 一号楼 |
| PURCHASER | 9 | 一号楼 |
| WAREHOUSE_MANAGER | 12 | 一号楼 |

测试采购物品为 2 台交换机，金额、数量和税率均使用字符串。账号和数据只存在于
`FakeBackendClient`，不写真实后端。

## 状态验收

```text
DRAFT
→ PENDING_REVIEW
→ REJECTED
→ PENDING_REVIEW
→ PENDING_PURCHASE
→ PURCHASING
→ PENDING_WAREHOUSE
→ COMPLETED
```

驳回后修改原采购单并调用 `resubmit-review`，不创建替代采购单。最终完成后
`current_handler` 清空。

## 并发、幂等与权限

Task 3～6 的永久回归测试覆盖旧 `expected_version`、确认前版本变化、非法候选、
跨楼宇/非处理人、字段不完整和重复 `action_token`。Task 2 HTTP 测试覆盖飞书
`event_id` 去重与相同通知 `dedup_key` 只发送一次。冲突时应用服务重新加载后端详情，
不覆盖新数据。

## 通知

业务状态成功不调用飞书跨角色主动发送。通知仅允许：

```text
backend notification_outbox worker
→ Notification Gateway
→ RendererRegistry
→ FeishuClient
```

飞书失败或 timeout 返回非 2xx，由后端 Outbox 决定有限重试；通知网关不调用业务流转
接口，所以不会重做或回滚已成功业务。

## 外部阻塞

- 正式 `event_type`、Payload 和生产卡片 Renderer 未冻结；
- 通知网关生产持久化幂等存储未选定；
- 未提供真实后端地址、四角色测试账号与隔离测试数据，未执行真实写入 smoke。

以上项目均未通过自创契约或绕过 Outbox 处理。
