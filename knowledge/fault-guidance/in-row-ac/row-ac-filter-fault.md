---
schema_version: 1
knowledge_id: IN-ROW-AC-FILTER-001
title: 列间空调滤网异常与更换引导
equipment_category: IN_ROW_AC
knowledge_type: FAULT_GUIDE
aliases:
  - FILTER BLOCKED
  - AIR FILTER ALARM
  - 滤网堵塞
  - 过滤器异常
risk_level: MEDIUM
status: ACTIVE
version: 1
---

# 列间空调滤网异常与更换引导

## 场景说明

本知识用于列间空调滤网或过滤器异常，并需要判断是否形成采购需求的场景。风量下降、压差变化或过滤报警不能单独证明滤网本体需要更换。

## 典型现象

- 列间空调出现 FILTER BLOCKED 或 AIR FILTER ALARM；
- 运维人员发现滤网污染、堵塞或破损；
- 现场检查确认滤网本体异常。

## 需要关注的信息

需要先排除仅为运行工况或其他部件造成的现象，并确认滤网本体、是否需要更换以及实际数量。

## 判断采购需求前建议确认的信息

- 已排除仅为外部工况或其他部件异常；
- 已确认列间空调滤网本体异常；
- 已确认需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `ROW_AC_FILTER`
- display_name: `列间空调滤网`
- procurement_category: `IN_ROW_AC`

如果只有风量或报警现象，应继续确认，不能自动形成滤网候选。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得依据设备安装滤网总数推断采购数量。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、尺寸、过滤等级、参数、兼容性或采购数量。

## 安全与人工介入

涉及设备停运、拆卸、检测或维修时，应由专业人员处理。本知识不提供现场操作步骤。
