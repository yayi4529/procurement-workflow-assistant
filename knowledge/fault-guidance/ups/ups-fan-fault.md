---
schema_version: 1
knowledge_id: UPS-FAN-001
title: UPS风扇故障与更换引导
equipment_category: UPS
knowledge_type: FAULT_GUIDE
aliases:
  - FAN FAULT
  - FAN FAILURE
  - 风扇故障
  - 风机报警
risk_level: LOW
status: ACTIVE
version: 1
---

# UPS风扇故障与更换引导

## 场景说明

本知识用于 UPS 出现风扇故障、风机报警，且需要逐步确认是否形成风扇采购需求的场景。仅有设备温度升高或散热异常，不能直接认定风扇本体损坏。

## 典型现象

- UPS 报告 FAN FAULT 或 FAN FAILURE；
- 运维人员观察到风扇停转、异响等现象；
- 现场检测确认某个风扇本体异常。

## 需要关注的信息

需要关注是否已经定位到具体风扇、是否由专业检测确认风扇本体故障、是否需要更换，以及异常风扇数量。设备安装的风扇总数不等于采购数量。

## 判断采购需求前建议确认的信息

- 已确认 UPS 风扇本体故障；
- 已确认故障风扇需要更换；
- 已确认需要更换的风扇数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `UPS_FAN`
- display_name: `UPS 风扇`
- procurement_category: `UPS`

如果只存在温度或散热现象，应继续确认具体故障部件，不能直接形成候选。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得根据 UPS 的风扇安装总数或知识经验推断采购数量。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、技术规格、参数、兼容性或采购数量。相同 canonical_item 不代表具体型号与当前 UPS 兼容。

## 安全与人工介入

涉及带电检测、拆卸或维修时，应由具备相应能力的专业人员处理。本知识不提供现场操作步骤。
