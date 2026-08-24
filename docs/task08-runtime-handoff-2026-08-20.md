# Task08 运行时修复交接（2026-08-20）

## 当前状态

- 分支：`codex-task06b-multi-item-workflow-agent`
- 基线提交：`71dcbae feat: add Task08 recommendations and expand fault knowledge`
- Backend：`http://127.0.0.1:8001`，Ready
- Agent：`http://127.0.0.1:8000`，Ready，当前 PID `28748`
- 当前改动尚未 commit、push；工作区还包含另一窗口的知识库改动，处理时不要覆盖。

## 本轮主要修复

1. 清理了旧 Agent 会话污染，新活动会话为 `93029`。
2. 新采购意图优先创建真实采购项，不再先走旧诊断或历史推荐接口。
3. 品牌、型号允许为空；新建采购项明确要求 `item_kind/item_name/quantity/unit`。
4. 兼容 DashScope 拒绝 `tool_choice=required`：首次 400/422 后移除该参数重试一次。
5. 普通故障描述可自动进入故障引导，无需强制使用“故障引导：”前缀：
   - `机房高温报警`
   - `2号UPS风扇报警，风扇不转`
   - `空调不制冷`
6. 排除非故障意图，如“采购报警器”“查询历史报警”。模糊异常可由 LLM 轻量分类。
7. 未经用户确认的数量不会被采用；数量证据不足时只追问数量，不要求重述全部信息。
8. 修复故障候选确认循环：
   - 新建或修改候选：`PROPOSE_ITEM`
   - 已有候选且用户确认：LLM 应返回 `DIRECT_TO_PROCUREMENT`
   - 用户修改物品、数量或单位：继续 `PROPOSE_ITEM`
   - 不采用代码看到“是”就直接创建草稿的方案。
9. 允许严格解析被标准 Markdown `json` 围栏包裹的 LLM JSON，剥离围栏后仍执行完整 Schema 校验。

## 真实模型验证

在状态 `AWAITING_CANDIDATE_CONFIRMATION`、候选为“UPS 风扇 × 2个”时，真实 DashScope 结果：

```text
是   → DIRECT_TO_PROCUREMENT
是的 → DIRECT_TO_PROCUREMENT
确认 → DIRECT_TO_PROCUREMENT
```

三次均未再次返回 `PROPOSE_ITEM`。

## 当前联调数据

- 已提交采购单：`PR-20260820-03CC377F`（ID `95137`）
- 状态：`PENDING_REVIEW`
- 采购项：UPS蓄电池 × 3块，品牌/型号为空
- 该单已不可编辑，不得建议向其追加风扇采购项。
- 当前故障上下文中已有安全候选：UPS 风扇 × 2个。

## 验证建议

在飞书当前会话直接回复：

```text
是
```

预期：LLM 返回 `DIRECT_TO_PROCUREMENT`，创建一张新的故障采购草稿并返回正式确认卡，不再重复“是否按这个采购需求继续”。

新故障可测试：

```text
机房高温报警
```

预期：自动进入故障引导，不要求特殊口令。

## 质量检查

最近一次完整结果：

```text
ruff format --check . 通过
ruff check .          通过
mypy src              通过
pytest -q             501 passed, 117 skipped
git diff --check      通过
```

## 注意事项

- 不要运行会重置联调数据库的 seed 测试；此前曾导致刚创建的需求立即消失。
- `seed_demo_data.py` 已调整为只清理 `TEST_PLATFORM` 身份，避免覆盖 FEISHU 绑定。
- 不要提交 `.env`、Redis 密码、飞书 Secret 或 LLM API Key。
- 正式提交、审批和状态流转仍必须通过正式卡片与后端执行，LLM 只负责理解、引导和候选预填。
