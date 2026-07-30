# Codex 单任务提示词模板

你现在需要在本仓库完成：

```text
<任务名称>
```

## 目标

<明确可运行结果>

## 必须遵守

- 卡片正式流程不得依赖 LLM；
- 后端是正式事实来源；
- 不直接访问 MySQL；
- Agent 会话通过后端接口管理；
- 修改字段使用 expected_version；
- 正式动作使用 action_token；
- 不静默创造接口和业务规则。

## 开发前

```bash
git status
git branch --show-current
git log -5 --oneline
```

阅读：

```text
AGENTS.md
CODEX_PROJECT_SPEC.md
相关 docs
```

## 实现范围

- Domain
- Port
- Application
- Adapter
- Interface
- DI
- Tests
- Docs

## 不做

<排除范围>

## 后端接口

<列出方法、路径、请求和响应>

## 测试

- 正常路径
- 权限失败
- 状态失败
- 版本冲突
- 重复动作
- 后端超时
- 飞书失败
- LLM 不可用时正式流程仍成功

## 质量检查

```bash
ruff format .
ruff format --check .
ruff check .
mypy src
pytest -q
git diff --check
git status --short
```

## 最终汇报

1. 开发前状态；
2. 实现结果；
3. 文件变更；
4. 调用链；
5. 接口映射；
6. 测试结果；
7. Git 状态；
8. 已知限制；
9. 待确认项。
