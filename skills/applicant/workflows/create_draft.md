---
name: create-draft
description: 从明确采购意图创建或修改一个多采购项草稿。
triggers: [我要买, 我要采购, 我要购买, 帮我买, 帮我采购, 买, 采购, 购买, 重新开始, 再买]
capabilities: [recommend_products_by_name, update_multi_item_draft]
stop-after-success: [update_multi_item_draft]
priority: 20
phases:
  - name: collect-items
    capabilities: []
    input-parser: applicant-items
    on-success: recommend-history
    on-failure: collect-items
    terminal-status: AWAITING_USER
  - name: recommend-history
    capabilities: [recommend_products_by_name]
    retry: 0
    on-success: await-selection
    on-failure: collect-reason
  - name: await-selection
    capabilities: []
    input-parser: applicant-candidate-selection
    on-success: collect-reason
    on-failure: await-selection
    terminal-status: AWAITING_USER
  - name: collect-reason
    capabilities: []
    input-parser: applicant-application-reason
    on-success: save-draft
    on-failure: collect-reason
    terminal-status: AWAITING_USER
  - name: save-draft
    capabilities: [update_multi_item_draft]
    retry: 0
    on-success: awaiting-card
    on-failure: FAILED
  - name: awaiting-card
    capabilities: []
    on-success: COMPLETED
    on-failure: FAILED
    terminal-status: AWAITING_CARD
---

# 创建采购草稿

## 适用条件

用户明确表达购买、采购或更换物品，并至少给出每项数量。

## 输入提取

为每项提取：物品名称、数量、采购项类型、可选品牌、可选型号、申请理由和资产引用。完整设备使用 `EQUIPMENT`，明确的风扇、电容等可更换部件使用 `COMPONENT`；不要省略 `item_kind`。不要要求需求人提供计量单位；由模型按语义选择，处理器继续提供确定性兜底。

## 执行流程

1. 判断这是新采购、追加、修改还是移除。
2. 用户说出采购商品名称后，先调用一次 `recommend_products_by_name` 查询历史采购品牌型号。
   有历史候选时只展示候选并等待用户选择，不得自动选择；没有历史候选时不展示推荐，直接继续原草稿流程。
3. 用户说“一个”“1个”“一台”等时保存数量 `1`。
4. 候选选择完成后先收集申请原因；此阶段的普通文本只填写当前草稿的
   `application_reason`，即使包含“故障”或“更换”也不得改道。只有明确出现
   “我要买/我要采购/我要购买/帮我买/帮我采购”的新采购句式才视为新目标。
5. 新采购或“重新开始”使用 `start_new=true` 和 `REPLACE`，避免旧草稿污染。
6. 一次把全部已确认物品交给 `ApplicantDraftSkillHandler.save`。
   已解析输入位于 `workflow_inputs.items_json`，必须按其中名称、数量、品牌、型号和目录 ID 原样构造唯一一次 `update_multi_item_draft` 调用。
7. 保存成功后展示同一采购单的正式确认卡，不再调用查询或推荐能力。

## 后端使用边界

处理器复用 `UpdateMultiItemDraftCapability`。该能力内部通过 BackendClient 获取当前身份、会话状态、创建或更新可编辑草稿，并使用版本控制保存多采购项。Skill 不直接调用提交、审批或状态流转接口。

## 停止条件

- 缺数量：只追问缺少数量的物品。
- 查到历史品牌型号：展示候选并等待选择。
- 没有历史品牌型号：不推荐，继续保存未带品牌型号的草稿。
- 草稿保存成功：立即结束并展示卡片。
- 权限、并发或后端错误：返回真实错误，不声称保存成功。
