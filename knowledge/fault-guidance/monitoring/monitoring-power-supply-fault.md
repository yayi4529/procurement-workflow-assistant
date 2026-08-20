---
schema_version: 1
knowledge_id: MONITORING-POWER-SUPPLY-001
title: 监控电源模块故障与更换引导
equipment_category: MONITORING
knowledge_type: FAULT_GUIDE
aliases:
  - POWER SUPPLY FAILURE
  - PSU FAULT
  - 监控电源故障
  - 电源模块报警
risk_level: MEDIUM
status: ACTIVE
version: 1
---

# 监控电源模块故障与更换引导

## 场景说明

本知识用于动环监控设备的电源模块已确认故障，并需要形成采购需求的场景。监控离线、主机断电或通信中断可能有多种原因，不能直接认定电源模块损坏。

## 典型现象

- 监控设备报告 POWER SUPPLY FAILURE 或 PSU FAULT；
- 运维人员报告监控电源模块异常；
- 现场检测确认电源模块本体故障。

## 需要关注的信息

需要关注是否已排除供电链路或其他监控部件问题、是否定位到电源模块、是否需要更换以及故障数量。

## 判断采购需求前建议确认的信息

- 已确认监控电源模块本体故障；
- 已确认故障模块需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `MONITORING_POWER_SUPPLY`
- display_name: `监控电源模块`
- procurement_category: `MONITORING`

如果只有监控离线或断电现象，应继续确认具体原因。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得根据监控设备数量推断采购数量。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、电气参数、技术规格、兼容性或采购数量。

## 安全与人工介入

涉及带电检测、拆卸或维修时，应由具备相应能力的专业人员处理。本知识不提供操作步骤。
