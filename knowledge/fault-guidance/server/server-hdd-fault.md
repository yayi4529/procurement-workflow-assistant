---
schema_version: 1
knowledge_id: SERVER-HDD-001
title: 服务器HDD故障与更换引导
equipment_category: SERVER
knowledge_type: FAULT_GUIDE
aliases:
  - HDD FAILURE
  - DRIVE FAILED HDD
  - HDD故障
  - 机械硬盘报警
risk_level: LOW
status: ACTIVE
version: 1
---

# 服务器HDD故障与更换引导

## 场景说明

本知识用于服务器 HDD 本体已经确认故障，并需要形成采购需求的场景。IO 变慢、应用性能下降、容量不足或硬盘指示灯异常不能直接证明 HDD 损坏。

## 典型现象

- 管理界面报告 HDD FAILURE 或明确的 HDD Drive Failed；
- 运维人员定位到具体机械硬盘异常；
- 现场检测确认 HDD 本体故障。

## 需要关注的信息

需要关注故障介质是否确认为 HDD 而不是 SSD、是否已定位具体故障盘、是否需要更换以及数量。

## 判断采购需求前建议确认的信息

- 已确认服务器 HDD 本体故障；
- 已确认故障 HDD 需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `SERVER_HDD`
- display_name: `服务器 HDD`
- procurement_category: `SERVER`

如果磁盘类型或本体故障尚未确认，应继续询问。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得根据盘位数、阵列规模或已安装磁盘总数推断。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、容量、接口、转速、兼容性或采购数量。

## 安全与人工介入

服务器停机、数据保护、检测、拆卸和维修应由专业人员处理。本知识不提供存储维护步骤。
