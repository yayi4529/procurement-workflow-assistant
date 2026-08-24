---
name: applicant
description: 处理采购需求人的采购草稿、故障转采购、产品候选和本人单据查询；不处理审批、采购执行或入库。
metadata:
  role: APPLICANT
---

# 需求人 Skill

当前角色必须来自采购后端，不能根据用户自述推断。只处理需求人可执行的查询、解释和候选草稿预填。

## 任务路由

- 明确购买一个或多个物品：读取 [workflows/create_draft.md](workflows/create_draft.md)。
- 描述故障并询问需要购买什么：读取 [workflows/fault_procurement.md](workflows/fault_procurement.md)。
- 按物品名称询问品牌或型号：读取 [workflows/product_recommendation.md](workflows/product_recommendation.md)。
- 查询本人采购单、状态或进度：读取 [workflows/status_query.md](workflows/status_query.md)。

每轮只选择一个主要 workflow。只有 workflow 明确要求时才读取其他 workflow；不要在取得足够证据后改道。

## 共同规则

- 业务事实必须来自 BackendClient 返回的证据。
- 用户明确给出的物品、数量和确认结果必须原样保留；未提供单位时按物品语义自动填写，不询问单位。
- 品牌、型号、兼容性、数量和故障原因不得猜测。
- 新采购意图不能复用已提交单据；建立新草稿并隔离旧任务上下文。
- 每轮最多执行一次草稿写入。写入只保存候选草稿，不提交采购流程。
- 正式提交、重新提交和处理人选择只能通过后端驱动的正式飞书卡片完成。

## 内部处理器

- 草稿保存由 `handlers/draft.py` 封装现有多采购项草稿能力。
- 产品候选由 `handlers/recommendation.py` 封装按名称推荐能力。
