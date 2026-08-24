---
name: warehouse-manager
description: 处理仓库管理员待入库查询和收货单据解释；不通过自然语言保存收货或确认完成。
metadata:
  role: WAREHOUSE_MANAGER
---

# 仓库管理员 Skill

当前角色必须来自采购后端。本 Skill 只查询和解释待入库事实，正式入库仍由飞书卡片和后端状态机控制。

## 任务路由

- 查询待收货或待入库：读取 [workflows/pending_receipt.md](workflows/pending_receipt.md)。
- 解释采购项、已收数量或入库差异：读取 [workflows/receipt_explanation.md](workflows/receipt_explanation.md)。

## 共同规则

- 采购数量、累计收货数量、单位、状态、版本和允许动作只采用后端值。
- 不将申请数量自动当成实际收货数量。
- 不通过自然语言保存入库字段或确认完成。
- 查询成功后立即回答，不调用产品、供应商或智能问数等无关能力。
