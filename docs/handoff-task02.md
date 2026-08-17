# Task 01–02 交接说明

当前分支：`codex-task02-procurement-agent`

## 已完成

- 建立 `CapabilityMetadata`、`CapabilityRegistry`、`CapabilityPolicy`。
- 全部现有文本 Tool 通过 Adapter 注册，Tool 名称和 Schema 保持不变。
- 文本主链路收敛为：

  ```text
  AssistantService
  → ProcurementAgent
  → CapabilityPolicy
  → AssistantRuntime
  → CapabilityRegistry / Tool
  ```

- 多角色用户按 `CurrentUser.roles` 获取 Capability 并集，不再依赖 `focused_role` 裁剪能力。
- `RoleIntentResolver`、`AgentRouter` 和四个旧 RoleAgent 已退出生产文本入口，但暂保留作兼容测试/迁移导入。
- 字段完整后的正式卡片呈现集中在 `LegacyToolResultPresenter`；提交、驳回、开始采购和完成仍只能通过正式卡片执行。

## 验证

```text
ruff format --check . 通过
ruff check . 通过
Task 01–02 范围 mypy 通过
pytest -q: 246 passed, 110 skipped
```

全量 mypy 仍有仓库既有测试类型错误，未阻塞本次生产代码和新增测试。

## 后续建议

下一步进入 Tool V2 重构前，先确认真实后端 OpenAPI 契约和文本 Agent 的多角色真实联调。不要在正式采购卡片路径中引入 LLM 状态流转。

当前未修改后端、未提交正式通知事件，也未接入 Redis/生产分布式锁。
