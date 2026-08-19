---
schema_version: 1
knowledge_id: BATTERY-UPS-BATTERY-001
title: 蓄电池资产中的UPS蓄电池故障与更换引导
equipment_category: BATTERY
knowledge_type: FAULT_GUIDE
aliases:
  - BATTERY FAILURE
  - CELL FAILURE
  - 蓄电池故障
  - 电池单体异常
risk_level: LOW
status: ACTIVE
version: 1
---

# 蓄电池资产中的UPS蓄电池故障与更换引导

## 场景说明

本知识用于故障来源资产本身属于 BATTERY，且现场需要确认是否形成 UPS 蓄电池采购需求的场景。它不同于以 UPS 为来源资产的 BATTERY FAULT 引导，但可以指向同一个标准采购对象。

## 典型现象

- 蓄电池检测报告指出电池单体异常；
- 运维人员报告蓄电池故障或失效；
- 已定位到服务于 UPS 的异常蓄电池。

## 需要关注的信息

需要关注蓄电池检测是否完成、异常对象是否确认为 UPS 蓄电池、是否需要更换，以及异常数量。报警或后备能力变化本身不能替代检测结论。

## 判断采购需求前建议确认的信息

- 已完成必要的蓄电池检测；
- 已确认 UPS 蓄电池本体故障；
- 已确认需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `UPS_BATTERY`
- display_name: `UPS 蓄电池`
- procurement_category: `BATTERY`

如果电池用途或故障对象尚未确认，应继续询问，不能把现象直接转换成采购项。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得根据电池组规模、安装总数或经验推断异常数量。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、电压、容量、规格、兼容性、是否整组更换或采购数量。canonical_item 只表示采购语义，不表示型号兼容。

## 安全与人工介入

蓄电池检测、带电操作、拆卸和维修应由具备相应能力的专业人员处理。本知识不提供操作方法。
