# V2.0 → V2.1 修改说明

根据后端接口 V1.5、数据库 V1.4 和 2026-07-30 联调说明，必须修改上一版 Codex 文档。

## 重大修改

1. 所有采购后端业务请求新增 HMAC 网关签名头。
2. 通知改为后端 notification_outbox + 后端 worker + 本项目通知网关。
3. 不再由业务接口成功响应直接触发下一角色通知，避免双发。
4. 新增采购时间线接口。
5. 楼长和采购员总价由后端计算校验。
6. review 首次保存创建 DRAFT，同轮保存更新，同轮通过/驳回完成。
7. 采购员新增 update_supplier_profile 明确确认。
8. 入库字段统一 received_quantity/receipt_remark，少收必须备注。
9. 黑名单仅能关联 COMPLETED 采购申请。
10. brand/model 后端当前为可选，不得阻止提交。
11. Agent messages 支持 GET 分页、duplicate 和 Redis 快照恢复。
