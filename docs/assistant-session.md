# Agent 会话设计 V1.5

## 1. 存储边界

- Redis：实时短期状态；
- MySQL：会话元数据、完整可见消息、关键快照；
- 正式业务表：采购事实。

本项目通过后端 HTTP 接口使用会话，不直接访问 Redis。

## 2. 接口

```text
POST     /api/v1/agent/conversations/active
POST/GET /api/v1/agent/conversations/{id}/messages
GET/PUT  /api/v1/agent/conversations/{id}/state
POST     /api/v1/agent/conversations/{id}/snapshot
POST     /api/v1/agent/conversations/{id}/complete
```

## 3. 规则

- 同一员工、同一 current_action 默认一个 ACTIVE 会话；
- `external_message_id` 在同一会话内唯一；
- POST messages 返回 duplicate；
- GET messages 默认 50、最大 200，按时间和 message_id 正序；
- Redis Key：`agent:session:{conversation_id}`；
- 默认 TTL：72 小时；
- 每次成功读取/更新刷新 TTL；
- Redis 丢失时从最新 MySQL 快照恢复；
- 无可恢复快照时返回 `SESSION_EXPIRED`；
- 不保存模型内部思维过程。

## 4. 会话状态边界

`collected_data` 只保存尚未写入后端的候选。后端 PATCH 成功后，正式字段、missing_fields、pending_field 和 version 均以后端响应为准。
