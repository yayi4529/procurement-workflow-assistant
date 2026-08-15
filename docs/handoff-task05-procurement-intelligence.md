# Task 05 交接说明

## 当前状态

- 分支：`codex-task02-procurement-agent`
- Task 05 已完成并接入 `CapabilityRegistry` / `CapabilityPolicy`。
- 未修改采购后端、数据库、Redis、正式卡片状态机或通知事件。

## 新增能力

- `diagnose_procurement_need`
- `find_similar_purchases`
- `compare_products`
- `compare_suppliers`

以上能力均为 `READ`，只返回结构化候选、证据、不确定性和缺失数据，不执行提交、驳回、开始采购或完成。

## Task 04 兼容基础设施

新增 `BusinessFacts`、`AgentTaskState`、`ReferenceStore` 及对应 Service。
当前通过现有 Backend Agent Session 的 `collected_data` 和 `last_recommendations` 持久化，后续若后端提供原生 V2 Schema，可替换 Adapter，不影响 Capability 接口。

## 排名与安全

- 历史采购：型号、品牌、设备、楼宇和时间的确定性排序。
- 产品比较：只使用已保存候选和历史采购证据。
- 供应商比较：重新读取供应商主数据；黑名单供应商硬阻断。
- 缺失交期、质量、故障率或实时价格时明确返回 `insufficient_data`，不编造。
- 申请理由辅助只使用用户已提供事实，不生成未知故障原因、金额或紧急等级。

## 验证

```text
ruff format --check . 通过
ruff check . 通过
mypy src 通过
pytest -q: 252 passed, 110 skipped
git diff --check 通过
```

## 后续建议

1. 与后端确认原生 TaskState / ReferenceStore V2 契约后，替换当前 Session 兼容映射。
2. 使用真实 OpenAPI 和隔离测试数据执行 intelligence smoke。
3. 继续观察真实 Agent 多步组合路径，不把诊断、历史、比较固定成工作流。
