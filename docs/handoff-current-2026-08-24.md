# 采购 Agent 当前交接（2026-08-24）

## 运行状态

- 分支：`codex-task06b-multi-item-workflow-agent`
- 基线提交：`71dcbae`
- Agent：`http://127.0.0.1:8000`，健康检查通过
- Backend：`http://127.0.0.1:8001`，Ready
- 飞书公网隧道：当前不可用，需要重新启动 Cloudflare Tunnel，并把新地址填入飞书开发者后台
- 工作区有未提交改动，勿执行 reset、clean 或覆盖其他窗口的修改

## 已完成

- Applicant 的创建草稿、故障采购、产品推荐已拆分为阶段化 Skill workflow。
- 新增统一阶段转换、只读阶段重试、同轮最多 3 个只读阶段和正式卡片完成观察器。
- workflow 状态保存于 `workflow_v1:state`，支持旧版本迁移。
- 增加统一证据引用：资产、历史采购、目录型号、推荐、分析查询和供应商。
- 正式卡片流程不经过 LLM；LLM 只能查询、解释、推荐和预填草稿。

## 验收结果

- Ruff、mypy、`git diff --check`：通过
- 普通测试：`402 passed, 36 skipped`
- 真实 LLM 第一轮：`6/6` 通过
- 第二轮真实 LLM：存在模型波动，尚未满足连续两轮全绿门槛

## 下一步

1. 重启 Cloudflare Quick Tunnel，更新飞书事件订阅地址为：`https://<新域名>/webhooks/feishu`。
2. 飞书发送：`我要买1个开关电源`，确认 webhook 能到达 Agent。
3. 继续验证故障多物品和“第一个”候选选择场景。
4. 修复真实 LLM 的重复工具调用、空响应和候选误改道后，再切换 strict 验收。

## 重要边界

正式提交、审批、采购、入库仍必须通过后端和飞书正式卡片；不要把 `.env`、密钥或完整飞书 Payload 写入日志或提交 Git。
