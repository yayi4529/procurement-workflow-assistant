---
name: fault-procurement
description: 根据故障、报警和资产证据提出候选部件并在确认后创建草稿。
triggers: [故障, 报警, 异常, 坏了, 损坏, 不能启动, 高温, 更换, 维修]
capabilities: [resolve_asset, get_asset_components, find_similar_purchases, recommend_products_by_name, update_multi_item_draft]
stop-after-success: [update_multi_item_draft]
priority: 30
phases:
  - name: identify-asset
    capabilities: [resolve_asset, get_asset_components]
    on-success: propose-parts
    on-failure: FAILED
  - name: propose-parts
    capabilities: [get_asset_components, find_similar_purchases, recommend_products_by_name]
    retry: 1
    on-success: confirm-replacements
    on-failure: confirm-replacements
  - name: confirm-replacements
    capabilities: []
    input-parser: applicant-confirmed-items
    on-success: save-draft
    on-failure: confirm-replacements
    terminal-status: AWAITING_USER
  - name: save-draft
    capabilities: [update_multi_item_draft]
    on-success: awaiting-card
    on-failure: FAILED
  - name: awaiting-card
    capabilities: []
    on-success: COMPLETED
    on-failure: FAILED
    terminal-status: AWAITING_CARD
---

# 故障引导采购

## 原则

故障现象、报警和知识文档只能产生候选部件，不能证明部件已经损坏。未经用户确认，不得写入采购草稿。

## 执行流程

1. 识别故障涉及的资产；必要时读取资产及主要部件事实。
2. 使用只读故障知识提出可能需要检查或更换的一个或多个候选物品。
3. 只追问一个关键问题：哪些候选已确认需要更换，以及每项数量。
4. 用户确认多个部件和数量后，一次保存为多个独立采购项。
   风扇、电容等更换件的 `item_kind` 使用 `COMPONENT`，并严格采用 `workflow_inputs.items_json` 的物品和数量。
   `source_asset_ref` 必须使用 `workflow_inputs.evidence_refs` 中的 `asset:<id>`，不得改写成资产编码或名称。
5. 单位自动填写；品牌、型号和兼容性只有得到历史、目录或用户证据时才填写。

## 禁止事项

- 不把报警直接写成“部件损坏”。
- 不默认数量为 `1`。
- 不因为某个查询为空就连续调用无关资产、历史或目录查询。
- 不通过自然语言提交草稿。

## 停止条件

候选尚未确认时停在澄清；全部物品和数量确认后保存一次草稿并结束。
