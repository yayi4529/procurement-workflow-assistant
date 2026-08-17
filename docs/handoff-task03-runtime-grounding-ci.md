# Task03 / Task03-B 交接

更新时间：2026-08-15
分支：`codex-task02-procurement-agent`

## 本次完成

- AssistantRuntime：单轮最多一次 MUTATE、terminal 结果立即停止、未知工具结构化处理、总工具调用上限和 observation 长度硬限制。
- Grounding：采购事实、历史采购、供应商/产品推荐与比较必须先取得相关后端能力证据；一般解释不强制调用工具。
- CI：拆分 assistant quality、integration/contract、backend quality；根项目覆盖 Python 3.11/3.12，后端独立安装并使用 MySQL/Redis 服务。
- 后端 Windows 环境补充条件依赖 `tzdata`。

## 验证

- 根项目：`pytest -q` → `277 passed, 110 skipped`
- 根项目：Ruff format、Ruff check、mypy 全部通过
- 后端：`pytest` → `43 passed`
- 后端：Ruff format/check 全部通过
- CI YAML 已通过 YAML 解析验证

真实 LLM eval 未启用；GitHub Actions 尚未在本次本地操作中实际运行。

## 架构边界

后端仍是采购业务唯一事实来源。正式提交、审批、驳回、采购和入库状态流转仍由确定性
飞书卡片及后端完成。未引入新的多 Agent 架构、意图路由器、数据库 Schema 或正式采购能力。

## 本地联调

Agent：`http://127.0.0.1:8000`

Backend：`http://127.0.0.1:8001`

Backend 测试依赖 MySQL/Redis；生产环境不得使用本地内存降级。

