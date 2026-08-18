# Task06 多采购项与轻量履约模型

Task06-A 将正式采购单从单一表头采购内容扩展为采购项、逐项评审、逐项采购执行和可追加收货。正式状态仍只有 `DRAFT`、`PENDING_REVIEW`、`REJECTED`、`PENDING_PURCHASE`、`PURCHASING`、`PENDING_WAREHOUSE`、`COMPLETED` 七种；履约状态由执行与收货数据实时派生，不新增状态机。

## 数据模型

仅新增两张采购业务表：

- `purchase_request_item`：采购项事实来源，支持商品、服务，可选设备分类、型号和来源资产；服务项默认不入库。
- `purchase_review_item`：按评审轮次保存采购项快照及建议供应商、估价、合同和到货建议。历史快照不随申请项后续展示字段变化。

现有表调整：

- `purchase_request` 增加 `request_type`、`source_asset_id`；旧表头字段仅用于兼容，不再是多项事实来源。
- `purchase_execution` 一项一条执行记录，以 `request_item_id` 唯一关联最终供应商和采购数量；V1 不允许拆单采购。
- `warehouse_receipt` 以 `execution_id` 关联执行，可多次追加收货。

两阶段 Alembic migration 先扩表与确定性回填，再建立非空、唯一、外键和检查约束。历史正式申请必须能按旧表头生成第 1 项；孤儿执行、孤儿收货或历史超收会中止迁移。降级会在多项、分批收货或无法还原旧单项结构时拒绝执行。

## HTTP 契约

所有接口继续使用 Gateway HMAC、后端身份、`expected_version` 和既有权限校验：

```text
PUT   /api/v1/requirements/{id}/items
PUT   /api/v1/requirements/{id}/review-items
PATCH /api/v1/requirements/{id}/purchase-items/{request_item_id}
POST  /api/v1/requirements/{id}/receipts
```

追加收货还必须携带稳定 `action_token`。事务内锁定采购执行，聚合既有收货量并拒绝超收；网络超时不得生成新 token 盲目重试。

详情响应增加 `request_type`、`source_asset_id`、`items`、`review_items`、`executions`、`receipts` 和 `request_fulfillment`。Root BackendClient 使用严格 DTO 和显式 Mapper；FakeBackend 提供同形能力。旧 applicant/review/purchase/warehouse 字段接口仅桥接单项场景，多项或已有分批收货时返回明确冲突，不静默丢数据。

## 业务规则

- 草稿和驳回态可整体替换采购项；进入评审后项目结构冻结。
- 提交评审至少存在一个有效采购项。
- 每轮评审生成独立快照；建议供应商可空，最终供应商在采购执行时逐项确定。
- 商品项及明确要求入库的服务项必须完成收货；普通服务项采购完成后跳过仓库。
- 单项履约状态由采购数量和累计收货量派生为未采购、待收货、部分收货或已完成。
- `complete` 只在全部需入库项足量收货后成功；任何累计收货量不得超过采购数量。

Task06-A 不包含 Agent/飞书多项编辑 UI、拆单采购、多资产故障诊断或库存占用，这些边界由后续任务另行设计。
