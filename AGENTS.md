# AGENTS.md

本文件是 Codex 在本仓库中工作的最高级项目约束。

## 1. 项目目标

开发一个基于飞书卡片和智能助手的采购流程自动化平台。

关键关系：

```text
卡片负责正式填写和确定性操作
Agent 负责查询、预填、解释和总结
后端负责正式字段、状态、权限、版本、幂等和审计
```

Agent 不是采购流程必经路径。

## 2. 强制边界

### 正式卡片路径不得依赖 LLM

下列操作不得经过 LLM：

- 保存正式字段；
- 提交楼长；
- 重新提交；
- 驳回；
- 提交采购员；
- 提交仓库；
- 确认入库；
- 拉黑或解除黑名单；
- 选择下一处理人。

### 后端是唯一事实来源

以下内容只能采用后端返回值：

- 身份；
- 角色；
- 楼宇；
- 正式字段；
- 缺失字段；
- 状态；
- 当前处理人；
- 允许动作；
- version；
- 供应商和黑名单；
- 统计数字。

### 数据访问

- 禁止直接访问 MySQL。
- Agent 会话默认通过后端 REST 接口管理 Redis。
- 若未来新增直接 Redis Adapter，必须由明确任务批准。
- 不允许将正式业务事实只存 Redis。

## 3. 稳定枚举

角色：

```text
APPLICANT
BUILDING_MANAGER
PURCHASER
WAREHOUSE_MANAGER
ADMIN
```

状态：

```text
DRAFT
PENDING_REVIEW
REJECTED
PENDING_PURCHASE
PURCHASING
PENDING_WAREHOUSE
COMPLETED
```

不得创建平行枚举。

## 4. 依赖方向

```text
interfaces/adapters
→ application
→ domain/ports
```

禁止：

```text
domain → FastAPI/httpx/lark_oapi
application → 具体飞书 SDK
card handler → LLM
LLM adapter → 业务数据库
```

## 5. Agent 规则

首版意图：

```text
SEARCH_RECORDS
PREFILL_REQUIREMENT
QUERY_STATUS
PROCESS_GUIDE
SUMMARIZE_RESULTS
SEARCH_CATALOG
CARD_HELP
```

要求：

- LLM 输出 Pydantic 强类型结构；
- 一次追问一个后端 `next_missing_field`；
- 推荐最多展示 3 项；
- 用户回复序号时使用 Redis 稳定引用；
- 正式保存前重新查询后端；
- 数字必须来自后端；
- Agent 不生成正式动作结果；
- Agent 不声称已提交，除非收到后端成功响应。

## 6. 卡片规则

- 卡片使用后端最新详情渲染；
- 字段保存携带 `expected_version`；
- 正式动作携带 `action_token`；
- 卡片不携带或信任操作人身份；
- 不信任卡片传入的角色和状态；
- 版本冲突后重新加载和刷新；
- “问智能助手”在当前机器人私聊窗口继续对话；
- 预填建议必须经过用户点击后才能应用；
- 应用建议时重新加载最新后端版本。

## 7. 请求规范

身份头：

```text
X-Platform-Type
X-Platform-User-Id
X-Request-Id
```

金额、数量和税率均使用字符串。

业务请求体不得传入操作者 ID。

## 8. 开发流程

开始前：

```bash
git status
git branch --show-current
git log -5 --oneline
```

完成前：

```bash
ruff format .
ruff format --check .
ruff check .
mypy src
pytest -q
git diff --check
git status --short
```

除非任务明确要求，不提交、不推送、不创建 PR。

## 9. 禁止规避

- 删除测试；
- 降低类型检查；
- 大量 `Any`；
- 无说明 `type: ignore`；
- 将后端错误吞掉后返回成功；
- 通知失败后重新执行正式业务；
- 静默创造后端未定义接口；
- 静默统一冲突字段。

## 10. 遇到冲突

数据库与接口字段不一致、流程不明确或接口缺失时：

1. 停止猜测；
2. 更新 `docs/open-decisions.md`；
3. 在最终报告中说明；
4. 等待业务和后端负责人确认。


## 11. 后端 V1.5 强制约束

- 所有业务请求必须由签名器添加 `X-Gateway-Timestamp`、`X-Gateway-Nonce`、`X-Gateway-Signature`。
- 签名路径不包含查询字符串。
- 跨角色通知只由后端 `notification_outbox` 驱动，业务响应不得直接触发第二次发送。
- 本项目必须提供平台无关通知网关，并按 `Idempotency-Key` 幂等。
- `brand`、`model` 当前为可选字段，不得阻止需求人提交。
- 楼长和采购员总价由后端计算校验。
- 楼长审核同轮只使用一条 `purchase_review`。
- 黑名单只能关联 `COMPLETED` 采购申请。
- 入库数量使用 `received_quantity`；少于申请数量时 `receipt_remark` 必填。
