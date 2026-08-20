---
schema_version: 1
knowledge_id: COOLING-PUMP-MECHANICAL-SEAL-001
title: 冷却泵机械密封故障与更换引导
equipment_category: COOLING_PUMP
knowledge_type: FAULT_GUIDE
aliases:
  - SEAL FAILURE
  - MECHANICAL SEAL LEAK
  - 机械密封损坏
  - 机封故障
risk_level: MEDIUM
status: ACTIVE
version: 1
---

# 冷却泵机械密封故障与更换引导

## 场景说明

本知识用于冷却泵机械密封已确认故障并需要更换的场景。冷却泵漏水只是现象，泄漏可能来自不同位置，不能直接判断为机械密封损坏。

## 典型现象

- 运维人员报告机械密封损坏或机封故障；
- 冷却泵出现泄漏现象；
- 现场检查已将故障定位到机械密封本体。

## 需要关注的信息

需要关注泄漏位置是否已经确认、故障是否定位到机械密封、是否需要更换，以及故障密封数量。

## 判断采购需求前建议确认的信息

- 已确认冷却泵机械密封本体故障；
- 已确认故障机械密封需要更换；
- 已确认需要更换的数量。

## 采购相关知识

只有上述事实全部成立时，才可以形成候选采购对象：

- canonical_item: `PUMP_MECHANICAL_SEAL`
- display_name: `水泵机械密封`
- procurement_category: `COOLING_PUMP`

如果用户仅报告漏水，应继续确认泄漏来源，不能自动形成机械密封候选。

## 数量规则

采购数量只能来自 USER_CONFIRMED、USER_EXPLICIT_REQUEST 或 BACKEND_FACT。不得根据泵数量或经验推断采购数量。

## 不应直接推断的内容

不得自行推断品牌、型号、Part Number、尺寸、材质、参数、兼容性或采购数量。

## 安全与人工介入

涉及停泵、隔离、拆卸和维修时，应由专业人员处理。本知识不提供泄压或拆装方法。
