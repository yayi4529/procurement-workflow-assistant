---
name: pending-receipt
description: 查询仓库管理员当前可见的待收货和待入库单据。
triggers: [待入库, 待收货, 待办, 入库列表, 哪些单据, 采购测试]
capabilities: [search_purchase_requests, get_purchase_request]
priority: 20
---

# 待入库查询

1. 使用 BackendClient `list_requirements` 查询仓库管理员可见的待办。
2. 打开目标单据时使用 `get_requirement` 获取最新采购执行和收货详情。
3. 展示采购项、实际采购数量、累计收货数量、单位、供应商和缺失字段。
4. 提供正式入库卡入口，不从自然语言写入或确认完成。

无待办是正常空结果，不描述成权限或后端故障。
