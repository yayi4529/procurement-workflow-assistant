---
name: requirement-explanation
description: 基于单据、历史和候选事实解释采购需求但不代替审批。
triggers: [解释, 为什么, 是否合理, 历史, 推荐, 品牌, 型号, 供应商, 详情]
capabilities: [get_purchase_request, get_purchase_timeline, find_similar_purchases, recommend_products_by_name, recommend_products, recommend_suppliers, get_supplier_profile, compare_products, compare_suppliers]
priority: 10
---

# 采购需求解释

1. 先读取目标采购单最新详情。
2. 根据用户问题选择必要证据：相似历史、产品候选、供应商资料或时间线。
3. 区分申请人陈述、后端事实和模型解释，不把候选推荐写成审批结论。
4. 数据缺少质量、故障率或交期时明确指出，不得推断。
5. 获得足够证据后立即总结，不切换到无关查询。

楼长草稿字段只能通过现有 `UpdateReviewDraftCapability` 预填；正式审核动作继续走卡片和 BackendClient 状态机。
