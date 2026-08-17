# Task 06 交接文档

更新时间：2026-08-15  
GitHub：<https://github.com/yayi4529/procurement-workflow-assistant>  
当前分支：`codex-task02-procurement-agent`  
最新提交：`beed51b docs: refresh monorepo readmes and ci formatting`

## 当前结构

项目已整理为单仓库：

```text
src/       Agent、飞书适配和正式卡片流程
backend/   FastAPI 采购后端、MySQL/Redis、Session、通知 Outbox
tests/     单元、集成、契约和 Agent Eval
```

文本 Agent 只负责查询、推荐、解释和草稿辅助；提交、驳回、开始采购、入库完成仍必须由
正式飞书卡片确定性执行。

## 本地启动

```powershell
# 后端依赖
cd backend
docker compose --env-file .env.docker up -d
python -m alembic upgrade head

# 后端：8001
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1

# 另开终端，Agent：8000
cd ..
.\scripts\start_http_integration.ps1 -EnvFile .env -BackendBaseUrl http://127.0.0.1:8001 -HostAddress 0.0.0.0 -Port 8000 -EnableLlm
```

检查地址：

```text
Agent:   http://127.0.0.1:8000/health/ready
Backend: http://127.0.0.1:8001/ready
OpenAPI: http://127.0.0.1:8001/openapi.json
Webhook: http://127.0.0.1:8000/webhooks/feishu
```

公网联调使用 Cloudflare Quick Tunnel，生成的域名是临时的；飞书后台填写公网域名加
`/webhooks/feishu`。

## 已完成

- Redis 分布式事件去重、会话锁和通知幂等。
- Production 禁止 memory/local 不安全降级。
- TaskState/ReferenceStore schema version 2。
- Agent turn、Capability 调用和错误的结构化日志。
- Agent Eval baseline、CI、Runbook 和 README 更新。
- Backend 已纳入根仓库 `backend/`。

## 验证结果

```text
ruff format --check . 通过
ruff check . 通过
mypy src 通过
pytest -q：259 passed, 110 skipped
GitHub Actions CI：success
```

## 注意事项

- `.env`、`.env.docker`、LLM/飞书/网关密钥不得提交。
- 真实后端契约以运行时 `/openapi.json` 为准。
- 生产环境必须使用 Redis-backed dedup、conversation lock 和 notification delivery。
- Legacy RoleAgent/Tool compatibility 文件仍被历史测试直接引用，暂未物理删除；生产主路径只使用 `ProcurementAgent`。
- 未执行真实生产 Smoke；需要隔离测试数据、真实 Feishu 身份和运行中的后端环境。
