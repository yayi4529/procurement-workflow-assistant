---
name: supplier-recommendation
description: 基于聚合历史与供应商资格事实生成供应商排名和建议。
triggers: [供应商, 供货商, 合作方, 黑名单, 交付周期, 合作次数, 供应商排名]
capabilities: [recommend_suppliers_with_evidence]
stop-after-success: [recommend_suppliers_with_evidence]
priority: 50
---

# 供应商推荐

## 固定流程

1. 从问题提取物品、品牌型号、时间范围和排名指标。
2. 使用采购项分析视图聚合 `supplier_id`、`supplier_name`、采购项次数、采购金额和平均交付周期。
3. 对结果中的候选供应商批量核验有效状态和黑名单事实。
4. 返回有证据的排名，说明空值、样本量、合成数据和截断状态。

## 规则

- 供应商统计必须走智能问数，不能使用 `find_similar_purchases` 代替。
- 供应商详情与黑名单核验使用 BackendClient 的供应商读取能力，由 Skill 内部适配器执行。
- 缺少质量或故障率字段时明确说明，不得把采购次数等同于质量。
- 排名只用于解释和候选推荐，不能自动写入正式采购单。

完成分析和资格核验后立即结束。
