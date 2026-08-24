---
name: status-query
description: 查询需求人可见采购单的状态、进度和时间线。
triggers: [采购单, 单据, 状态, 进度, 到哪了, 谁在处理, 时间线, 历史单据]
capabilities: [search_purchase_requests, get_purchase_request, get_purchase_timeline]
priority: 10
---

# 采购单状态查询

## 执行流程

1. 有采购单号时精确查询；没有时按当前需求人的可见范围检索。
2. 用户询问具体单据时重新获取详情，不依赖列表中的不完整字段。
3. 只采用后端返回的状态、当前处理人、缺失字段、版本和时间线。
4. 用业务语言解释当前环节和下一步可用动作。

## 后端能力映射

- 列表检索：BackendClient `list_requirements`。
- 单据详情：BackendClient `get_requirement`。
- 流转记录：BackendClient `get_requirement_timeline`。

这些是 Skill 内部适配器的实现依据，不应逐个注册为全局 LLM 工具。

## 停止条件

取得目标单据事实后立即回答；多条同名结果时让用户选择采购单号。
