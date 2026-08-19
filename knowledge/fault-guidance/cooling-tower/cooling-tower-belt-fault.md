---
schema_version: 1
knowledge_id: COOLING-TOWER-BELT-001
title: 冷却塔皮带故障与更换引导
equipment_category: COOLING_TOWER
knowledge_type: FAULT_GUIDE
aliases:
  - BELT FAILURE
  - BELT BROKEN
  - 皮带断裂
  - 传动皮带异常
risk_level: MEDIUM
status: ACTIVE
version: 1
---

# 冷却塔皮带故障与更换引导

## 场景说明

本知识用于冷却塔传动皮带已出现故障，并需要确认采购需求的场景。风机不转、转速异常或设备振动可能有多种原因，不能直接认定皮带损坏。

## 典型现象

- 运维人员报告皮带断裂、明显损伤或传动异常；
- 冷却塔出现 BELT FAILURE；
- 专业检查确认传动皮带本体故障。

## 需要关注的信息

需要关注故障是否定位到皮带本体、是否确认需要更换、涉及的皮带数量。不能用冷却塔风机数量推导采购数量。

## 判断采购需求前建议确认的信息

- 已确认冷却塔皮带本体故障；
- 已确认故障皮带需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `COOLING_TOWER_BELT`
- display_name: `冷却塔皮带`
- procurement_category: `COOLING_TOWER`

如果只有振动、转速或风机异常，应继续确认具体故障部件。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得根据常见传动结构或安装数量推断。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、长度、规格参数、兼容性或采购数量。

## 安全与人工介入

冷却塔旋转机械的检测、停机、拆卸和维修应由专业人员处理。本知识不提供机械操作步骤。
