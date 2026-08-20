---
schema_version: 1
knowledge_id: ROOM-TEMP-HUMIDITY-SENSOR-001
title: 机房温湿度传感器故障与更换引导
equipment_category: ROOM_ENVIRONMENT
knowledge_type: FAULT_GUIDE
aliases:
  - TEMP HUMIDITY SENSOR FAULT
  - SENSOR OFFLINE
  - 温湿度传感器故障
  - 温湿度探头异常
risk_level: LOW
status: ACTIVE
version: 1
---

# 机房温湿度传感器故障与更换引导

## 场景说明

本知识用于机房温湿度传感器本体已确认异常，并需要形成采购需求的场景。机房温度或湿度超限可能是真实环境变化，不能直接判断传感器损坏。

## 典型现象

- 传感器报告 SENSOR OFFLINE 或自身故障；
- 温湿度读数异常或缺失；
- 现场检测确认温湿度传感器本体异常。

## 需要关注的信息

需要排除真实环境变化、通信链路或监控系统问题，确认传感器本体故障、是否需要更换以及数量。

## 判断采购需求前建议确认的信息

- 已排除仅为真实环境变化或外部链路异常；
- 已确认温湿度传感器本体故障；
- 已确认需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `ROOM_TEMP_HUMIDITY_SENSOR`
- display_name: `温湿度传感器`
- procurement_category: `ROOM_ENVIRONMENT`

如果只有高温或高湿报警，应继续确认，不能自动形成传感器候选。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得根据机房监测点总数推断采购数量。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、量程、精度、接口、兼容性或采购数量。

## 安全与人工介入

涉及设备检测、拆卸或维修时，应由专业人员处理。本知识不提供诊断阈值或操作步骤。
