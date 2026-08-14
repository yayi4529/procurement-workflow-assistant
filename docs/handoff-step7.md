# 第七步交接：Tooling 与安全多角色切换

## 状态

- 分支：`default`
- 范围：Tooling 可维护性整理 + 安全自然语言多角色切换
- 正式采购卡片和 Backend 状态流转边界保持不变。

## 已完成

- 将原 `agent_tools.py` 按职责拆分到 `assistant/tooling/` 的 common、Applicant、BuildingManager、Purchaser、Warehouse 模块。
- `agent_tools.py` 保留为兼容导出 facade，旧 import 路径继续可用。
- 新增 `RoleIntentResolver`：仅在多角色且已有 focused role 时调用。
- Resolver 只接收 `CurrentUser.roles` 中的候选角色，并通过编号映射；AgentRouter 和 ToolPolicy 继续做确定性权限校验。
- HIGH 置信度才切换 focused role；LOW、歧义、越界、非法输出或 LLM 故障均保持当前角色。
- 第六步 Eval 增加多角色 Case，以及 Role Selection Accuracy、Unnecessary Role Switch、Unauthorized Role Selection 指标。

## 验证

```text
ruff format/check 通过
mypy src 通过
228 passed, 110 skipped
tests/evals: 10 passed, 80 skipped
git diff --check 通过
```

真实 LLM Eval 未启用；需要显式设置 `RUN_LLM_EVALS=1`，并提供项目 LLM 配置。

## 安全边界

- Resolver 不能新增、修改或提升用户角色。
- 一次只运行一个 RoleAgent，不引入 Agent-to-Agent、Planner 或 Supervisor。
- 正式审批、采购、入库完成等动作仍只能通过 Card/Workflow。
- 用户原有 `outputs/` 和 handoff 文件未纳入本次提交。
