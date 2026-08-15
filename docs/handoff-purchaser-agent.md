# PurchaserAgent 交接文档

更新时间：2026-08-14

## 当前版本

- 分支：`default`
- 最新提交：`f43c59f refactor purchaser agent to observation loop`
- 代码已推送到 GitHub。

## 本次完成

- PurchaserAgent 已删除采购单号、供应商资料和实际单价的 Python 关键词/Regex 路由。
- 自然语言理解交给 LLM，业务真实性和权限校验由 Tool/Backend 负责。
- `prepare_purchase_prefill`、`fill_selected_supplier_profile` 和未完成的草稿保存结果会回到 Observation Loop。
- 精确供应商主数据由 Backend 直接写入草稿，不经过 LLM 抄写。
- 草稿字段完整后重新读取 Backend 最新详情，并展示正式采购员卡片。
- 正式开始采购、提交仓库等状态操作仍只能通过正式飞书卡片完成。
- 采购员 Working Context 增加采购执行草稿，同时不直接暴露税号和银行账号。

## 主要文件

- `src/procurement_platform/application/assistant/agents/purchaser.py`
- `src/procurement_platform/application/assistant/prompts/purchaser.py`
- `src/procurement_platform/application/assistant/agent_tools.py`
- `src/procurement_platform/application/assistant/context_composer.py`
- `tests/unit/test_task9_agent_tools.py`

## 验证结果

```text
194 passed, 30 skipped
ruff format/check 通过
mypy src 通过
git diff --check 通过
```

## 启动和联调

- 本项目：`http://127.0.0.1:8000`
- Agent：`http://127.0.0.1:8003`
- 后端：`http://127.0.0.1:8001`
- 文本 Agent 默认关闭；需要显式设置 `PROCUREMENT_LLM_ENABLED=true`。
- Cloudflare Quick Tunnel 重启后地址会变化，需同步更新飞书回调地址。

## 注意事项

- Backend 是业务事实唯一来源。
- 不要让文本 Agent 执行正式采购状态转换。
- 不要删除或提交用户原有的 `outputs/`。
- 当前 `docs/handoff-latest.md` 包含用户原有修改，修改时需谨慎保留。
- WarehouseAgent 和四角色 Draft Result 统一本次未处理。
