# Task05 交接说明

更新时间：2026-08-17

## 工作区与分支

- 工作区：`D:\procurement-workflow-assistant`
- 分支：`codex-task05-data-center-assets`
- Task05 已完成并已推送提交：`ffb04cc`
- 当前前端观察台修改尚未提交

## 已完成内容

- 新增设备资产域 5 张表：
  - `equipment_category`
  - `equipment_model`
  - `asset`
  - `asset_component`
  - `asset_relation`
- 完成 Alembic migration、Backend 查询 API、Root BackendClient、Agent 资产查询能力和测试。
- 新增开发 Demo 的「设备资产域」只读观察台。
- 修复资产搜索参数：前端使用后端真实参数 `q`。

## 当前数据库数据

Docker 容器：

- MySQL：`127.0.0.1:3307`
- Redis：`127.0.0.1:6380`

已执行 migration 和南京江北新区智算中心合成数据导入：

```text
equipment_model：33
asset：600
asset_component：3654
asset_relation：1799
```

这批数据是合成开发数据，不代表真实中国移动 CMDB。资产 ID 范围为 `970001–970600`。

导入文件来源：

```text
C:\Users\lenovo\Downloads\seed_njdc_asset_data.py
C:\Users\lenovo\Downloads\njdc_task05_dataset.json
```

脚本支持幂等导入；只有明确执行 `--clean` 才会清理这批资产。

## 前端入口

```text
http://127.0.0.1:8001/demo/
```

操作：

1. 强制刷新页面：`Ctrl + F5`
2. 切换「系统管理员」身份，可查看全部资产
3. 点击左侧「06 设备资产域」
4. 搜索 `NJDC` 查看 600 台资产
5. 点击底部分类可筛选资产，点击资产可查看部件、关系和冗余同伴

## 当前服务状态

- `/health`：正常
- `/ready`：正常
- Task05 资产 API：已验证可用

## 后续注意

- 前端三个文件有未提交修改：`backend/frontend/index.html`、`app.js`、`styles.css`。
- 提交前执行 `git status`，不要把 `.venv`、日志或用户已有修改带入提交。
- 不要执行 `git reset --hard` 或 `git clean -fd`。
- 资产数据写入的是本地 Docker 数据卷；重建数据卷会丢失本地开发数据。
