---
schema_version: 1
knowledge_id: SERVER-MEMORY-001
title: 服务器内存故障与更换引导
equipment_category: SERVER
knowledge_type: FAULT_GUIDE
aliases:
  - DIMM ERROR
  - MEMORY ERROR
  - 内存故障
  - 内存报警
risk_level: LOW
status: ACTIVE
version: 1
---

# 服务器内存故障与更换引导

## 场景说明

本知识用于服务器报告 DIMM ERROR、MEMORY ERROR，且需要确认是否形成内存采购需求的场景。应用异常、服务器重启或性能下降不能单独证明内存本体损坏。

## 典型现象

- 服务器管理界面报告 DIMM ERROR 或 MEMORY ERROR；
- 运维人员报告具体内存条故障；
- 现场检测确认内存本体异常。

## 需要关注的信息

需要关注是否已定位具体故障内存、是否确认需要更换，以及故障内存数量。服务器已安装内存总数不能作为采购数量。

## 判断采购需求前建议确认的信息

- 已确认服务器内存本体故障；
- 已确认故障内存需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `SERVER_MEMORY`
- display_name: `服务器内存`
- procurement_category: `SERVER`

如果只有性能或重启现象，应继续确认具体故障部件。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得根据插槽数或已安装内存条数量推断。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、容量、频率、规格、兼容性或采购数量。

## 安全与人工介入

服务器停机、检测、拆卸和维修应由专业人员处理。本知识不提供拆装步骤。
