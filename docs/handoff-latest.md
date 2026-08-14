# 简单交接文档

更新时间：2026-08-14

## 当前状态

- 仓库：`D:\procurement-workflow-assistant`
- 分支：`default`
- Agent：`http://127.0.0.1:8003`
- 后端：`http://127.0.0.1:8001`
- 公网地址：`https://dozen-reply-fascinating-sufficiently.trycloudflare.com`
- 飞书回调：`https://dozen-reply-fascinating-sufficiently.trycloudflare.com/webhooks/feishu`
- 大模型：通义千问 `qwen-plus`

## 本轮完成

- BuildingManagerAgent 已去除中文关键词、序号别名、联系人和日期 Regex 等规则解析。
- 自然语言理解交给 LLM，真实供应商、权限、状态和候选引用由 Tool/Backend 校验。
- `update_review_draft` 支持通过 `selection_index` 安全选择最近推荐的供应商。
- 普通 Tool 成功结果回到 Observation Loop；审核字段完整后展示正式楼长卡片。
- 增加 LLM 超时降级回复，避免飞书消息静默无响应。

## 验证

- 全量测试：`205 passed, 13 skipped`
- 超时降级相关测试：`27 passed`
- Ruff、mypy 和 `git diff --check` 已通过。

## 注意事项

- 当前代码已提交并推送到 GitHub 的 `default` 分支。
- `outputs/` 是用户原有未跟踪目录，不要删除或提交。
- Cloudflare Quick Tunnel 地址重启后会变化，变化后需要同步修改飞书回调地址。
- 正式审批、驳回和提交采购员仍只能通过正式飞书卡片完成，不经过 LLM。
