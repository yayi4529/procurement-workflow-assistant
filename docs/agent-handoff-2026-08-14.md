# Agent 智能化改造交接（2026-08-14）

## 当前状态

- 仓库：`D:\procurement-workflow-assistant`
- 分支：`chore/feishu-fake-debug-harness`
- 基线提交：`a4c82ca`（已推送；本轮改动未提交、未推送）
- Agent：`http://127.0.0.1:8003` 当前不可访问，需要重新启动
- 工作区：存在本轮代码改动及新增 `context_composer.py`；`outputs/` 是用户原有未跟踪目录，请勿删除或提交

## 已完成

- ApplicantAgent 和 Applicant Prompt 已大幅精简，删除自然语言别名枚举及主要规则式判断。
- 新增 `AgentContextComposer`，动态注入当前采购单、状态、缺失字段、候选引用和近期对话历史。
- 普通 Tool Result 尽量交回 Runtime，由 LLM 观察后决定下一步；无历史推荐时改为主动询问用户偏好。
- Agent 的文本答复和追问统一使用飞书卡片。
- 已实现 CardKit JSON 2.0 同卡创建、更新、结束及普通卡片降级；仅展示整理后的步骤和工具状态，不保存或暴露隐藏思维链。
- 正式采购状态流转仍由既有卡片和 BackendClient 确定性执行，不经过 LLM。

## 验证结果

最近一次完整检查：`ruff format --check .`、`ruff check .`、`mypy src`、`git diff --check` 均通过；`pytest -q` 为 **203 passed、13 skipped**（另有 1 条既有弃用警告）。文档更新后未重新执行全量测试。

## 待办与联调重点

1. 在飞书开放平台确认并发布 CardKit 写权限（至少 `cardkit:card:write`），然后做真实卡片创建、更新和结束 Smoke。
2. 当前流式体验主要是“处理中”到最终答案的同卡更新；如需更细进度，应给 Runtime 增加安全的阶段/工具状态事件，不输出模型原始推理。
3. 可优化 tenant token 缓存、更新节流、重试与 CardKit 失败观测。
4. 重启 Agent 后先检查 `/ready`，再通过飞书验证多轮历史理解、无推荐数据追问、正式业务卡片分流和降级路径。
5. 确认功能后再提交；不要包含 `outputs/`。

## 建议启动与检查

以仓库现有启动方式运行 Agent（端口 `8003`），随后访问：

```text
http://127.0.0.1:8003/ready
```

公网 Cloudflare 地址可能已失效，重启 tunnel 后应同步更新飞书事件回调 URL。
