---
name: receipt-explanation
description: 解释采购数量、累计收货数量、差异和入库状态。
triggers: [收货, 入库, 数量, 差异, 少了, 到货, 剩余, 完成, 详情]
capabilities: [get_purchase_request, get_purchase_timeline]
priority: 10
---

# 入库单据解释

1. 获取目标采购单最新详情，不使用历史消息中的旧版本。
2. 逐采购项比较实际采购数量、已收数量和剩余数量；金额和数量使用后端值进行 Decimal 安全展示。
3. 区分部分收货、全部收货和后端定义的缺失字段。
4. 出现数量冲突或并发修改时刷新详情，不覆盖后端。
5. 保存收货和确认完成必须通过正式卡片，并携带最新 `expected_version` 与稳定动作令牌。
