---
schema_version: 1
knowledge_id: COOLING-PUMP-BEARING-001
title: 冷却泵轴承故障与更换引导
equipment_category: COOLING_PUMP
knowledge_type: FAULT_GUIDE
aliases:
  - BEARING FAILURE
  - BEARING FAULT
  - 轴承故障
  - 泵轴承异常
risk_level: MEDIUM
status: ACTIVE
version: 1
---

# 冷却泵轴承故障与更换引导

## 场景说明

本知识用于冷却泵轴承已经由现场检查确认异常，并需要形成采购需求的场景。噪声、振动或温升可能来自多个部件，不能仅凭现象认定轴承损坏。

## 典型现象

- 冷却泵出现异常噪声、振动或轴承相关报警；
- 运维人员报告泵轴承异常；
- 专业检测确认轴承本体故障。

## 需要关注的信息

需要关注是否已定位到轴承本体、是否确认需要更换，以及实际故障轴承数量。泵的轴承安装总数不等于采购数量。

## 判断采购需求前建议确认的信息

- 已确认冷却泵轴承本体故障；
- 已确认故障轴承需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `PUMP_BEARING`
- display_name: `水泵轴承`
- procurement_category: `COOLING_PUMP`

如果只有振动、噪声或温升现象，应继续确认具体故障部件。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得根据泵结构或经验推断数量。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、尺寸、材料、技术参数、兼容性或采购数量。

## 安全与人工介入

旋转机械的检测、拆卸和维修应由具备相应能力的专业人员处理。本知识不提供现场操作步骤。
