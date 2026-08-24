---
name: product-recommendation
description: 基于目录和采购历史生成品牌型号或产品候选。
triggers: [产品, 品牌, 型号, 产品推荐, 推荐产品, 推荐一下, 控制电源, 开关电源]
capabilities: [recommend_products_by_name, recommend_products, compare_products, find_similar_purchases]
priority: 20
---

# 产品推荐

1. 按用户提供的物品名称或采购项读取目录和历史候选。
2. 需要历史采购次数、金额或趋势时，使用采购智能问数 workflow，不用相似采购代替聚合统计。
3. 根据真实候选综合品牌、型号、历史次数和价格；兼容性无证据时标注待确认。
4. 空结果只表示当前业务数据没有候选，不要求用户重复提供系统能够查询的信息。
5. 用户选择候选后只做采购执行字段的候选预填；正式保存和开始采购走卡片。

取得候选或确认无候选后立即结束。
