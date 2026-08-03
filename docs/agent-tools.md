# Task 9 Agent 工具

文本 Assistant 默认关闭，只能通过 `PROCUREMENT_LLM_ENABLED=true` 显式启用。身份、角色、
楼宇、状态、处理人、版本和字段始终来自采购后端；候选引用存入后端 Agent session。

## 角色矩阵

| 角色 | 工具 |
| --- | --- |
| `APPLICANT` | `query_purchase_requests`、`recommend_product_options`、`update_purchase_draft` |
| `BUILDING_MANAGER` | `query_purchase_requests`、`recommend_suppliers_for_requirement`、`update_review_draft` |
| `PURCHASER` | `query_purchase_requests`、`query_supplier_profile`、`prepare_purchase_prefill`、`update_purchase_execution_draft` |
| `WAREHOUSE_MANAGER` | `query_purchase_requests`、`update_warehouse_receipt_draft` |

## 关键语义

- `query_purchase_requests` 支持搜索、详情和 timeline。相对日期由
  `TemporalRangeResolver` 按本地时区解析为左闭右开区间；业务节点时间必须以 timeline 确认。
- 商品、供应商和多匹配查询返回稳定候选引用。后续工具只接受本会话保存的引用，避免让
  LLM 猜测后端主键。
- `query_supplier_profile` 的统一社会信用代码、开户行、银行账号、注册地址、合同联系方式
  和黑名单状态由确定性渲染器输出，不经过模型改写。
- `prepare_purchase_prefill` 只使用楼长已选供应商。供应商主数据为精确来源；采购历史只能
  产生推荐或歧义候选，税率永不标为精确值。
- 三个草稿更新工具都会重新读取详情、检查当前处理人和状态，并携带最新
  `expected_version` 保存。金额使用 `Decimal`，采购总价采用后端返回值。
- 所有正式流转动作继续只存在于卡片流程。Task 9 工具不会提交楼长、驳回、提交采购员、
  开始采购、提交仓库或确认完成。

## 主动采购预填

后端 Outbox 发送 `REQUIREMENT_PENDING_PURCHASE` 时，通知网关可调用独立预填提供器生成
采购员建议卡。任何后端错误、权限或状态不匹配、缺少已选供应商都会回退到原待办通知。
预填不写正式字段，也不会触发业务状态转换。
