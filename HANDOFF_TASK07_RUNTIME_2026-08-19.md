# Task07 运行时交接

## 当前代码

- 仓库：`https://github.com/yayi4529/procurement-workflow-assistant`
- 分支：`codex-task06b-multi-item-workflow-agent`
- 最新提交：`e99a93f feat: wire Task07 fault guidance into Feishu runtime`
- 工作区：已提交并推送

本次已完成 Task07-A/B/C、Task07 飞书运行时接线，以及多项目草稿完成后直接返回正式确认卡片的修复。

## 本地服务

- Backend：`http://127.0.0.1:8001`
- Agent：`http://127.0.0.1:8000`
- MySQL：`127.0.0.1:3307`
- Redis：`127.0.0.1:6380`

后端和 Agent 依赖 Docker Desktop。Redis 启用了密码认证，Agent 启动时必须使用后端 `backend/.env.docker` 中的 `REDIS_PASSWORD`，不要把密码写入代码或提交到 Git。

## 重启步骤

```powershell
cd D:\procurement-workflow-assistant\backend
docker compose --env-file .env.docker up -d
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
```

另开 PowerShell 启动 Agent。下面命令会从后端环境文件读取 Redis 密码，不打印密码：

```powershell
cd D:\procurement-workflow-assistant
$line = Get-Content .\backend\.env.docker | Where-Object { $_ -match '^REDIS_PASSWORD=' } | Select-Object -First 1
$password = $line.Substring('REDIS_PASSWORD='.Length).Trim().Trim([char]34).Trim([char]39)
$env:PROCUREMENT_REDIS_URL = 'redis://' + ':' + [Uri]::EscapeDataString($password) + '@127.0.0.1:6380/1'
.\scripts\start_http_integration.ps1 -EnvFile .env -BackendBaseUrl http://127.0.0.1:8001 -HostAddress 127.0.0.1 -Port 8000 -EnableLlm -EnableFaultGuidance
```

验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/ready
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

## 飞书公网地址

当前 Quick Tunnel 地址：

```text
https://describe-targets-moms-males.trycloudflare.com/webhooks/feishu
```

飞书开放平台的事件订阅地址必须使用当前有效的 Quick Tunnel 地址。电脑重启、关闭 cloudflared 窗口或隧道断开后，地址可能变化，需要重新启动：

```powershell
cloudflared tunnel --protocol http2 --url http://127.0.0.1:8000
```

## 飞书测试

需求人发送：

```text
故障引导：一号楼二层2号UPS出现 BATTERY FAULT，需要更换3块南都2V 100Ah蓄电池
```

补充信息后发送“确认”，应创建后端 `DRAFT` 并返回“采购申请确认”卡片。正式提交仍通过卡片按钮完成。

## 已验证

- `ruff format --check .`：通过
- `ruff check .`：通过
- `mypy src`：通过
- `pytest -q`：358 passed，117 skipped
- Agent Redis 认证：`PONG`

## 注意事项

- 不要提交 `.env`、Redis 密码、飞书 App Secret 或 LLM API Key。
- Quick Tunnel 仅用于临时联调，不是固定生产公网地址。
- 后端代码位于同一根仓库的 `backend/` 目录；本次提交没有修改后端业务代码。
