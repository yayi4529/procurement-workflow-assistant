---
name: pending-purchase
description: 查询采购员当前可见的待采购单据和详情。
triggers: [待采购, 待办, 采购列表, 哪些单据, 当前单据, 单据详情, 采购测试]
capabilities: [search_purchase_requests, get_purchase_request, get_purchase_timeline]
priority: 10
---

# 待采购查询

1. 使用 BackendClient `list_requirements` 查询当前采购员可见的待办。
2. 用户打开单据时调用 `get_requirement` 获取最新状态、处理人和版本。
3. 展示采购项、需求与审核字段、缺失字段和后端允许动作。
4. 如需候选产品或供应商，明确转入对应 workflow，并终止当前 workflow。
5. 开始采购、保存采购执行字段和提交仓库必须由正式卡片调用后端。
