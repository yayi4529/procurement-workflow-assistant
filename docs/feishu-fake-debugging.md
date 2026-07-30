# 真实飞书 + Fake Backend 调试

该模式使用真实飞书机器人和正式卡片流程，但业务后端为进程内
`FakeBackendClient`。不启动采购后端、MySQL、Redis 或 LLM。

## 飞书开放平台

1. 为企业自建应用开启机器人能力。
2. 将四个测试账号加入有限可用范围。
3. 开通接收机器人单聊消息和以机器人身份发送消息的权限，核对
   `im:message.p2p_msg:readonly`、`im:message:send_as_bot` 或控制台当前等价权限。
4. 每次修改权限、能力或范围后发布测试版本。
5. 订阅 `im.message.receive_v1`。事件订阅和卡片回调均使用公网 HTTPS 地址加
   `/webhooks/feishu`。

如果机器人私聊窗口没有输入框，依次检查事件订阅、单聊读取权限和应用版本是否发布。

## Windows 启动顺序

```powershell
Copy-Item .env.feishu-fake.example .env.feishu-fake
New-Item -ItemType Directory -Force .local
Copy-Item examples/fake-users.example.json .local/fake-users.json
python scripts/validate_feishu_fake_config.py --env-file .env.feishu-fake
.\scripts\start_feishu_fake.ps1 -EnvFile .env.feishu-fake -HostAddress 0.0.0.0 -Port 8000
```

填写 `.env.feishu-fake` 中的真实飞书配置和随机通知网关 Token。文件已被 Git 忽略。
另开终端启动已安装的 Cloudflare Tunnel：

```powershell
.\scripts\check_local_service.ps1
.\scripts\start_feishu_tunnel.ps1 -Provider cloudflared
.\scripts\check_public_service.ps1 -BaseUrl https://example.trycloudflare.com
```

配置飞书 Webhook 后，让四个账号分别私聊机器人发送精确命令 `调试身份`。把回复中的
`platform_user_id` 替换进 `.local/fake-users.json`，然后重启服务。普通日志中的 open_id
会被掩码；完整 open_id 只回复给发起探针的当前用户。

重启后，各账号私聊机器人发送精确命令 `采购测试`：需求人收到采购首页，其余角色收到
各自待办列表。该入口是确定性开发命令，不经过 LLM。

## 通知 Smoke

```powershell
.\scripts\run_notification_smoke.ps1 `
  -BaseUrl https://example.trycloudflare.com `
  -ReceiverOpenId ou_xxxxx
```

`send` 应返回 204 并收到一张测试卡；`duplicate` 返回 204 且不重复发卡；
`conflict` 返回 409；`unauthorized` 返回 401。`DEV_NOTIFICATION_TEST` 不是正式通知
契约，也不会调用采购状态流转接口。

## 四角色人工流程

依次用需求人、楼长、采购员、仓库管理员完成创建提交、审核、采购和入库，并验证非处理人
无法操作、候选人正确、版本冲突刷新，以及重复事件不会重复执行。

Fake 状态和内存幂等记录在重启时丢失。必须保持单 worker，不能使用 reload。Quick
Tunnel URL 变化后需要同步更新飞书控制台。停止时在服务和隧道终端按 `Ctrl+C`。
