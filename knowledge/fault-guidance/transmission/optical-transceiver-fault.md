---
schema_version: 1
knowledge_id: TRANSMISSION-OPTICAL-TRANSCEIVER-001
title: 传输光模块故障与更换引导
equipment_category: TRANSMISSION
knowledge_type: FAULT_GUIDE
aliases:
  - OPTICAL MODULE FAILURE
  - TRANSCEIVER FAULT
  - 光模块故障
  - 光模块失效
risk_level: LOW
status: ACTIVE
version: 1
---

# 传输光模块故障与更换引导

## 场景说明

本知识用于传输设备光模块本体已经检测确认故障，并需要形成采购需求的场景。端口 Down、链路中断或光功率异常可能来自光纤、端口、板卡或其他原因，不能直接认定光模块损坏。

## 典型现象

- 设备报告 OPTICAL MODULE FAILURE 或 TRANSCEIVER FAULT；
- 传输端口 Down 或链路异常；
- 排查外部链路后，现场检测确认光模块本体故障。

## 需要关注的信息

需要关注是否已排除光纤和外部链路问题、是否确认光模块本体故障、是否需要更换以及故障数量。

## 判断采购需求前建议确认的信息

- 已排除仅为光纤、端口或其他外部链路异常；
- 已确认光模块本体故障；
- 已确认需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `OPTICAL_TRANSCEIVER`
- display_name: `光模块`
- procurement_category: `TRANSMISSION`

如果用户只报告端口 Down，应继续确认，不能自动形成光模块候选。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得根据端口数量或链路结构推断采购数量。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、速率、波长、接口、传输距离、兼容性或采购数量。

## 安全与人工介入

光链路检测、设备拆卸和维修应由具备相应能力的专业人员处理。本知识不提供操作步骤或参数阈值。
