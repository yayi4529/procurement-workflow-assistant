---
schema_version: 1
knowledge_id: SHU-FILTER-001
title: SHU过滤器异常与更换引导
equipment_category: SHU
knowledge_type: FAULT_GUIDE
aliases:
  - FILTER DIRTY
  - FILTER BLOCKED
  - 过滤器堵塞
  - 滤网异常
risk_level: LOW
status: ACTIVE
version: 1
---

# SHU过滤器异常与更换引导

## 场景说明

本知识用于 SHU 出现过滤器或滤网异常，并需要判断是否形成过滤器采购需求的场景。风量变化、压差变化或过滤器报警只是现象，不能单独证明过滤器本体必须更换。

## 典型现象

- SHU 报告 FILTER DIRTY 或 FILTER BLOCKED；
- 运维人员发现滤网污染、破损等现象；
- 现场检查确认过滤器本体异常。

## 需要关注的信息

需要先排除仅由运行工况或其他部件造成的现象，并确认过滤器本体状态、是否需要更换以及数量。

## 判断采购需求前建议确认的信息

- 已排除仅为外部工况或其他部件异常；
- 已确认 SHU 过滤器本体异常；
- 已确认需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `SHU_FILTER`
- display_name: `SHU 过滤器`
- procurement_category: `SHU`

如果只有风量或报警现象，应继续确认，不能自动推荐过滤器。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得依据 SHU 的滤网安装数量推断采购数量。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、尺寸、过滤等级、技术参数、兼容性或采购数量。

## 安全与人工介入

涉及设备停运、拆卸、检测或维修时，应由具备相应能力的专业人员处理。本知识不提供维修步骤。
