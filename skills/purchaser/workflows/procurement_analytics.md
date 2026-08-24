---
name: procurement-analytics
description: 对采购事实执行受控聚合 SQL 并根据结果回答统计问题。
triggers: [统计, 排行, 趋势, 汇总, 多少, 次数, 总数量, 金额, 平均, 每月, 各物品, 全部采购单, 智能问数]
capabilities: [analyze_procurement]
stop-after-success: [analyze_procurement]
priority: 30
---

# 采购智能问数

## 固定流程

1. 调用 `analyze_procurement`；该 Handler 内部读取受控语义目录。
2. Handler 仅使用目录中的分析视图和字段生成一条聚合 SQL。
3. Handler 执行只读 SQL；校验失败时根据真实错误最多修正一次。
4. SQL 成功后关闭全部能力，根据结果输出表格和结论。

## 后端能力映射

- 语义目录：BackendClient `get_analytics_catalog`。
- 只读查询：BackendClient `run_analytics_query`。

内部执行必须保留查询 ID、规范化 SQL、是否包含合成数据、截断状态和统计口径。不得逐张展开采购单进行汇总。

## 禁止改道

读取目录后，下一步只能执行分析 SQL；不能切换到资产、相似采购或普通推荐。SQL 成功后不得再次查询。
