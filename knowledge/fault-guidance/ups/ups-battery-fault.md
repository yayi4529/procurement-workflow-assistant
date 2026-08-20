---
schema_version: 1
knowledge_id: UPS-BATTERY-001
title: UPS蓄电池异常与BATTERY FAULT
equipment_category: UPS
knowledge_type: FAULT_GUIDE
aliases:
  - BATTERY FAULT
  - 电池报警
  - 蓄电池异常
  - 电池故障
  - 后备时间下降
risk_level: MEDIUM
status: ACTIVE
version: 1
---

# UPS蓄电池异常与BATTERY FAULT

## 场景说明

用于描述 UPS 出现 BATTERY FAULT、电池报警、蓄电池异常或后备时间明显下降等情况。

## 典型现象

- UPS出现BATTERY FAULT告警；
- 运维人员发现部分蓄电池异常；
- UPS后备时间明显下降。

## 需要关注的信息

判断是否可能形成蓄电池采购需求时，可以关注是否已经完成检测以及检测结果。

## 判断采购需求前建议确认的信息

- 是否已经完成蓄电池检测；
- 是否确认存在异常蓄电池；
- 如果存在异常蓄电池，异常数量是多少。

## 采购相关知识

如果现场检测已经确认存在异常蓄电池，并且明确需要进行更换，可以形成蓄电池更换类采购需求。

只有上述事实成立时，才可以形成以下候选采购对象：

- canonical_item: `UPS_BATTERY`
- display_name: `UPS 蓄电池`
- procurement_category: `BATTERY`

如果已经明确异常蓄电池数量，该数量可以作为候选采购数量。

如果数量尚未明确，不应自行推断采购数量。

## 数量规则

采购数量必须来自用户明确确认、用户明确采购要求或 Backend 已确认事实。不得默认数量为 1，
不得根据常见安装数量或知识经验推断采购数量。

## 不应直接推断的内容

没有可靠信息支持时，不得自行推断：

- 蓄电池品牌；
- 蓄电池型号；
- 电压；
- 容量；
- 与当前UPS的兼容性；
- 整组蓄电池是否必须更换；
- 采购数量。

## 安全与人工介入

涉及带电操作、拆卸、维修或其他高风险现场操作时，应由具备相应能力的专业人员处理。
