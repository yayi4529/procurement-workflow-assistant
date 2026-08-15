# Assistant Domain Capabilities

文本 Assistant 默认关闭，只能通过 `PROCUREMENT_LLM_ENABLED=true` 显式启用。身份、角色、
楼宇、状态、处理人、版本和字段始终来自采购后端；候选引用存入后端 Agent session。

## Capability V2

LLM 只看到现实采购业务动作。采购单查询拆为 `search_purchase_requests`、
`get_purchase_request` 和 `get_purchase_timeline`，schema 不包含 `operation` 二级路由。
旧 `query_purchase_requests` 仅作为内部兼容包装，不注册到 `CapabilityRegistry`。

当前能力按领域组织：

| 领域 | LLM-visible capabilities |
| --- | --- |
| 需求 | `search_purchase_requests`、`get_purchase_request`、`get_purchase_timeline` |
| 商品 | `recommend_products` |
| 供应商 | `get_supplier_profile`、`recommend_suppliers`、`apply_supplier_profile_to_draft` |
| 采购辅助 | `prepare_purchase_prefill` |
| 草稿 | `update_applicant_draft`、`update_review_draft`、`update_purchase_draft`、`update_warehouse_draft` |
| 采购智能 | `diagnose_procurement_need`、`find_similar_purchases`、`compare_products`、`compare_suppliers` |

采购智能能力来自后续任务并保留；它们同样只查询、诊断或比较，不执行正式流转。实际可见
集合由 `CapabilityMetadata.allowed_roles` 和当前后端用户角色决定。

## 关键语义

- `PurchaseRequestQueryService` 提供 search/detail/timeline 三个显式内部入口；旧 operation
  wrapper 只服务兼容测试和迁移调用。
- 商品、供应商和多匹配查询返回稳定候选引用。后续能力只接受当前会话保存的引用，避免
  让 LLM 猜测后端主键。
- `get_supplier_profile` 的统一社会信用代码、开户行、银行账号、注册地址、联系方式和
  黑名单状态来自后端，并由确定性 presenter 输出。
- `prepare_purchase_prefill` 只生成建议，不保存字段。供应商主数据为精确来源；采购历史
  只能产生推荐或歧义候选，税率永不标为精确值。
- 四个草稿能力都会重新读取详情、检查处理人和状态，并携带后端最新版本保存；它们不会
  自动执行下一业务动作。

## 正式动作边界

`submit`、`reject`、`resubmit`、`start purchase`、`submit warehouse` 和 `complete` 均不在
`CapabilityRegistry`。调用链保持为：

```text
Feishu Card → Action Router → Application Service → BackendClient → Backend
```

草稿完成后由 `ResultPresenter` 获取 authoritative detail 并展示对应正式卡片，用户必须在
卡片中明确操作。`action_token`、正式动作的 `expected_version` 与后端状态机语义未改变。
