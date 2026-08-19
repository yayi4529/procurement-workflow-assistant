---
schema_version: 1
knowledge_id: SERVER-POWER-SUPPLY-001
title: 服务器电源故障与更换引导
equipment_category: SERVER
knowledge_type: FAULT_GUIDE
aliases:
  - PSU FAILURE
  - POWER SUPPLY FAILURE
  - 服务器电源故障
  - 电源模块报警
risk_level: MEDIUM
status: ACTIVE
version: 1
---

# 服务器电源故障与更换引导

## 场景说明

本知识用于服务器电源或 PSU 本体已经确认故障，并需要形成采购需求的场景。服务器掉电、无法启动或电源告警可能来自外部供电、配电链路或其他部件，不能直接认定 PSU 损坏。

## 典型现象

- 管理界面报告 PSU FAILURE 或 POWER SUPPLY FAILURE；
- 运维人员定位到具体服务器电源模块异常；
- 现场检测确认服务器电源本体故障。

## 需要关注的信息

需要关注是否排除外部供电问题、是否定位到具体 PSU、是否确认需要更换以及故障数量。

## 判断采购需求前建议确认的信息

- 已确认服务器电源本体故障；
- 已确认故障电源需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `SERVER_POWER_SUPPLY`
- display_name: `服务器电源`
- procurement_category: `SERVER`

如果只有掉电或无法启动现象，应继续确认具体原因。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得根据服务器冗余电源总数推断采购数量。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、功率、电气参数、规格、兼容性或采购数量。

## 安全与人工介入

涉及供电检测、停机、拆卸或维修时，应由具备相应能力的专业人员处理。本知识不提供带电操作步骤。
