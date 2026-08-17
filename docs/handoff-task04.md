# Task04 交接

更新时间：2026-08-17

## 唯一推荐工作区

```text
D:\procurement-workflow-assistant
```

项目结构：

```text
Agent 代码：src/
Agent 测试：tests/
后端代码：backend/app/
后端测试：backend/tests/
```

不要再使用独立后端仓库 `D:\procurement-agent-backend` 作为后续开发入口。

## Git 状态

```text
仓库：yayi4529/procurement-workflow-assistant
分支：codex-task02-procurement-agent
提交：d0ac868 feat: harden agent correctness and performance
```

该提交已经推送到 GitHub。未创建 PR。

## 已完成内容

- 历史采购查询移除逐条详情请求，避免 N+1。
- 产品/供应商比较使用真实后端证据，黑名单供应商不能胜出。
- 产品引用优先使用稳定 `product_id`。
- 重复消息支持直接索引查询，即时、历史重放和并发场景至多执行一次 Agent。
- LLM client 复用、关闭、错误分类和有限重试已完成。
- CI 增加覆盖率门禁，当前总覆盖率约 82%，门禁为 80%。
- Task04 测试和架构/契约文档已补齐。

## 本地服务

```text
Agent：  http://127.0.0.1:8000
Backend：http://127.0.0.1:8001
MySQL： 127.0.0.1:3307
Redis：  127.0.0.1:6380
```

8001 已重启，健康检查通过。LLM 默认关闭，正式采购状态流转仍只走确定性卡片和后端。

## 验证结果

```text
Unit：        265 passed, 30 skipped
Integration： 4 passed
Contract：    18 passed
Eval：        10 passed, 80 skipped（真实 LLM 未启用）
Backend：     43 passed
Ruff / mypy： 通过
```

## 后续注意

- 后续只在 `D:\procurement-workflow-assistant` 工作。
- 修改后端时修改 `backend/`，不要复制独立后端仓库内容。
- 提交前检查 `git status`，不要带入 `.venv`、日志或用户已有 notification 修改。
- 不要执行 `git reset --hard`、`git clean -fd`。
