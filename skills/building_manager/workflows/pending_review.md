---
name: pending-review
description: 查询楼长当前被授权处理的待审核采购需求。
triggers: [待审核, 待办, 需要审核, 审核列表, 哪些单据, 采购测试]
capabilities: [search_purchase_requests, get_purchase_request]
priority: 20
---

# 待审核查询

1. 通过 BackendClient `list_requirements` 查询 `PENDING_FOR_ME`，让后端实施楼宇与角色过滤。
2. 打开单据时使用 `get_requirement` 获取最新详情和版本。
3. 展示申请人、楼宇、采购项、申请理由、缺失字段和当前状态。
4. 不从自然语言执行驳回或提交；提供正式审核卡入口。

查询成功或确认无待办后立即结束。不要把空结果描述为权限故障。
