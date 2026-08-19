---
schema_version: 1
knowledge_id: SERVER-FAN-001
title: 服务器风扇故障与更换引导
equipment_category: SERVER
knowledge_type: FAULT_GUIDE
aliases:
  - FAN FAULT
  - FAN FAILURE
  - 服务器风扇故障
  - 风扇模块报警
risk_level: LOW
status: ACTIVE
version: 1
---

# 服务器风扇故障与更换引导

## 场景说明

本知识用于服务器风扇本体已经确认故障，并需要形成采购需求的场景。服务器温度升高、散热异常或降频可能有多种原因，不能直接认定风扇损坏。

## 典型现象

- 管理界面报告 FAN FAULT 或 FAN FAILURE；
- 运维人员定位到具体风扇模块异常；
- 现场检测确认服务器风扇本体故障。

## 需要关注的信息

需要关注是否定位到具体风扇、是否确认需要更换，以及故障风扇数量。服务器安装风扇总数不能作为采购数量。

## 判断采购需求前建议确认的信息

- 已确认服务器风扇本体故障；
- 已确认故障风扇需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `SERVER_FAN`
- display_name: `服务器风扇`
- procurement_category: `SERVER`

如果只有温度或散热现象，应继续确认具体故障部件。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得根据服务器风扇总数推断采购数量。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、尺寸、转速、接口、兼容性或采购数量。

## 安全与人工介入

服务器停机、检测、拆卸和维修应由专业人员处理。本知识不提供拆装步骤。
