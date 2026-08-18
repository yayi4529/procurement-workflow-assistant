# Task06-B 飞书联调交接说明

更新时间：2026-08-18 15:28（Asia/Shanghai）

## 1. 工作区与 Git 状态

- 实际工作区：`D:\procurement-workflow-assistant`
- 当前分支：`codex-task06b-multi-item-workflow-agent`
- 当前基线提交：`ffb04cc feat: add data center asset domain and agent awareness`
- Task06-A、Task06-B、Task05 前端观察台和本次飞书修复均尚未提交。
- 工作区存在大量已修改和未跟踪文件，均应视为用户现有工作，不要覆盖、stash 或批量清理。
- 未执行 commit、push 或 PR。
- 禁止执行 `git reset --hard`、`git clean -fd`，不要删除或重建 Docker 数据卷。

开始后先执行：

```powershell
Set-Location D:\procurement-workflow-assistant
git status --short
git branch --show-current
git log -8 --oneline
```

## 2. 当前服务状态

当前本地拓扑：

```text
飞书 Quick Tunnel
→ webhook-only proxy 127.0.0.1:8003
→ Agent 0.0.0.0:8000
→ Backend 127.0.0.1:8001
→ MySQL 127.0.0.1:3307
→ Redis 127.0.0.1:6380
```

当前监听：

- Agent `8000`：PID `29788`
- Backend `8001`：PID `27368`
- Webhook proxy `8003`：PID `16424`
- Quick Tunnel Webhook：`https://cement-beads-damages-naturally.trycloudflare.com/webhooks/feishu`

健康检查：

- `http://127.0.0.1:8000/health/ready`：`ready`
- `http://127.0.0.1:8001/ready`：MySQL、Redis 均为 `ok`
- Agent 当前为 `backend_mode=http`、飞书已启用、LLM 已启用、身份调试探针关闭。

Agent 启动方式：

```powershell
.\scripts\start_http_integration.ps1 `
  -EnvFile .env `
  -BackendBaseUrl http://127.0.0.1:8001 `
  -HostAddress 0.0.0.0 `
  -Port 8000 `
  -EnableLlm
```

运行日志：

```text
.local/agent-d.stderr.log
.local/agent-d.stdout.log
.local/webhook-proxy.stderr.log
.local/cloudflared.stderr.log
```

## 3. 飞书测试身份

```text
楼长：       ou_1b706cd21f22664d8d8543300907f8c2 → 90002 / BUILDING_MANAGER
需求人：     ou_3da4d0e3765ebe815eae094a70e0ca8d → 90001 / APPLICANT
采购员：     ou_3aa1271accd7642d1b3f0d25adb8d7bd → 90003 / PURCHASER
仓库管理员： ou_181fb1f4d15a557abca07402af468c18 → 90004 / WAREHOUSE_MANAGER
```

不要在日志中输出 Secret、Token 或完整敏感配置。

## 4. 当前 Task06 测试单据与会话

- Agent conversation ID：`93012`
- Requirement ID：`91121`
- 单号：`PR-20260818-9717C620`
- 当前状态：草稿（DRAFT）
- 申请原因：替换故障设备
- 请求类型：`PURCHASE`
- 采购项：
  1. 液冷 AI 智算服务器，型号 `SRV-AI-LC-8ACC`，数量 `2 台`，类型 `EQUIPMENT`
  2. 上门安装服务，数量 `1 套`，类型 `SERVICE`
- 后端采购项 ID：`98020`、`98021`

此前该会话的 `purchase_request_id` 丢失，已通过现有 `BackendClient` HTTP 接口补齐为 `91121`，没有直连数据库，也没有触发正式提交。

## 5. 本轮飞书正式卡片问题及修复

### 5.1 Agent 返回 Markdown 文本而不是正式卡片

根因有两层：

1. `ApplicantAgent` 没有处理完整的 `UpdateMultiItemDraftResult`；
2. 用户直接说“确认当前多采购项草稿，返回正式确认卡片”时，LLM 不一定调用草稿工具。

已修复：

- `application/assistant/agents/applicant.py`：完整多采购项工具结果直接返回 `AssistantInteractionResponse`。
- `application/assistant/service.py`：申请人确认卡请求走确定性路由，不再依赖 LLM 是否选中工具。
- `application/assistant/task_context_service.py` 和 `tooling/multi_item.py`：保存多采购项草稿时同步持久化 `purchase_request_id`。

### 5.2 正式卡片生成后飞书返回 230099

日志确认路由和后端读取均成功，但飞书回复失败：

```text
code 230099
ErrCode: 11310
ErrPath: ROOT -> elements -> form -> elements -> button
ErrMsg: name(applicant_remove_item) duplicate
```

根因：两条采购项生成两个 `applicant.remove_item` 按钮，旧 Renderer 把两者的表单 `name` 都渲染为 `applicant_remove_item`。

已修复：

- `adapters/feishu/interaction_renderer.py`：同一表单内重复按钮名称增加稳定序号，例如 `applicant_remove_item_2`；业务 `action_id` 和按钮 value 不变。
- `adapters/feishu/sdk_client.py`：安全保留飞书错误 message 和 log_id，方便定位具体卡片 Schema 错误，不记录 Secret。
- 修复后已主动发送同一张卡，飞书返回 `delivered=True`。

### 5.3 卡片看起来没有预填信息

根因：确认请求仍复用了旧版单采购项 `detail()` 编辑卡。Task06 正式数据保存在 `items[]`，旧 `device_name/brand/model/quantity/unit` 输入框自然为空，造成“未预填”的错觉。

最新修复：

- `ApplicantCardFactory.detail()` 新增 `confirmation_mode`。
- Task06 Agent 完成草稿和直接确认路由均使用 `confirmation_mode=True`。
- 确认卡标题为“采购申请确认”。
- 卡片展示完整请求头和全部活动采购项。
- 不再显示空白旧版单项输入框，也不显示新增/移除编辑控件。
- 保留“准备提交”按钮；正式提交仍经过原有确定性卡片链路。

注意：这项“确认模式”修复已经完成、测试通过并重启 8000，但交接前尚未收到用户对最新卡片外观的最终确认。新窗口第一件事应让用户再次发送测试消息并查看日志。

## 6. 建议立即验证

需求人向机器人发送：

```text
确认当前多采购项草稿，返回正式确认卡片
```

预期：

1. 返回标题为“采购申请确认”的飞书正式卡片；
2. 显示采购类型 `采购`；
3. 显示申请原因“替换故障设备”；
4. 显示液冷 AI 智算服务器 `2 台`；
5. 显示上门安装服务 `1 套`；
6. 不出现空白的旧版设备名称、品牌、数量等输入框；
7. 显示“准备提交”和“我的申请”按钮；
8. 点击“准备提交”后进入楼长候选及最终确认链路，不由 LLM 直接提交。

同步观察：

```powershell
Get-Content D:\procurement-workflow-assistant\.local\agent-d.stderr.log -Wait -Tail 100
```

若再次失败，重点确认：

- 是否收到新的 `feishu_event_received`；
- 是否读取 conversation `93012` 和 requirement `91121`；
- 飞书 API 是否返回 200；
- 是否出现新的 `230099` 具体子错误；
- 飞书重试事件是否因相同 external message ID 被幂等处理。

## 7. 已执行测试

本轮实际结果：

```text
Task06-B 多采购项集成测试：3 passed
飞书 Renderer + Channel + Task06-B：9 passed
确认模式 + Applicant Workflow + Renderer：12 passed
Ruff：All checks passed
git diff --check：无空白错误，仅有既有 LF/CRLF 警告
```

更早的 Task06 全量结果：

```text
Root pytest：306 passed, 117 skipped
Backend pytest：58 passed
Alembic head：b6f11c06a002
```

最新小修后尚未重新执行整个仓库全量 pytest；提交前应按 `AGENTS.md` 再执行完整质量检查。

## 8. 本轮重点修改文件

```text
src/procurement_platform/application/assistant/agents/applicant.py
src/procurement_platform/application/assistant/service.py
src/procurement_platform/application/assistant/task_context_service.py
src/procurement_platform/application/assistant/tooling/multi_item.py
src/procurement_platform/application/applicant/card_factory.py
src/procurement_platform/adapters/feishu/interaction_renderer.py
src/procurement_platform/adapters/feishu/sdk_client.py
tests/unit/test_task06b_multi_item_integration.py
tests/unit/test_feishu_renderer.py
```

Task06 其余核心文件详见当前 `git status`，不要只提交上述列表而遗漏 Task06-A/B 的其他变更。

## 9. 安全与业务边界

- Agent 只维护 DRAFT 草稿，不得直接执行正式提交。
- 正式提交、审批、采购、入库仍由卡片 Action Router → Application Service → BackendClient 完成。
- 后端是身份、角色、字段、状态、版本、处理人和履约事实的唯一来源。
- Root 项目不得直连 MySQL/Redis。
- 不要输出 `.env`、`.env.docker` 中的密码、Token 或 Secret。
- 不要删除 `.env`；当前运行依赖 `D:\procurement-workflow-assistant\.env`。
- 不要重建 Docker 数据卷；本地 Task05/Task06 数据均在现有卷中。

## 10. 下一窗口建议顺序

1. 阅读根目录 `AGENTS.md` 和本文档。
2. 确认工作区、分支、服务和日志。
3. 让需求人再次发送确认卡测试消息。
4. 验证卡片预填展示和“准备提交”按钮。
5. 继续跑申请人 → 楼长 → 采购员 → 仓库管理员的多采购项 E2E。
6. 完成后运行 `ruff format --check .`、`ruff check .`、`mypy src`、`pytest -q`、`git diff --check`。
7. 提交前仔细拆分和复核工作区，不包含 `.env`、`.env.docker`、`.local`、日志、虚拟环境或用户无关修改。
