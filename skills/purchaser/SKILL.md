---
name: purchaser
description: 处理采购员的数据分析、产品和供应商推荐及待采购查询；不通过自然语言执行开始采购、保存正式采购或提交仓库。
metadata:
  role: PURCHASER
---

# 采购员 Skill

当前采购员身份必须来自采购后端。本 Skill 负责分析、解释、推荐和候选预填，不接管正式采购状态机。

## 任务路由

- 统计、排行、趋势、金额或跨单据分析：读取 [workflows/procurement_analytics.md](workflows/procurement_analytics.md)。
- 品牌型号或产品候选：读取 [workflows/product_recommendation.md](workflows/product_recommendation.md)。
- 供应商排名或推荐：读取 [workflows/supplier_recommendation.md](workflows/supplier_recommendation.md)。
- 查询待采购单据：读取 [workflows/pending_purchase.md](workflows/pending_purchase.md)。

每轮只选择一个主要 workflow。除非该 workflow 明确规定，不得在智能问数、相似历史和推荐能力之间改道。

## 共同规则

- 推荐和分析必须显示统计口径并基于后端证据。
- 品牌、型号、价格、供应商、采购次数和交付表现不得猜测。
- 黑名单和供应商有效状态必须使用后端权威事实核验。
- 查询成功后停止工具调用并总结。
- 开始采购、保存正式执行字段、提交仓库只能通过正式卡片。
