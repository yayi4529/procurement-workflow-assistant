# Data Center Fault Knowledge Taxonomy V1

## 1. Purpose

This taxonomy aligns the 17 data-center asset categories, Task07 Procurement Vocabulary, and the current Fault Knowledge Markdown schema. It plans Fault Topics, minimum confirmed facts, and future knowledge files. It is a knowledge-asset design document, not a runtime schema, diagnosis engine, repair guide, or batch Knowledge generation task.

Stable chain: `Asset → equipment_category → Fault Knowledge → Confirmed Facts → canonical_item → CandidateItem → user confirmation → PurchaseRequestItem`. Future historical matching and product/supplier ranking may join only through canonical item and are outside Knowledge-01.

## 2. Sources of Truth

1. Equipment categories: Backend `equipment_category.category_code`, seeded by `backend/scripts/seed_demo_data.py` (5 level-1 domains, 17 level-2 categories).
2. Procurement objects: `docs/task07-procurement-vocabulary-v1.md` canonical items, display names, and procurement aliases.
3. Runtime knowledge schema: existing `knowledge/fault-guidance/ups/ups-battery-fault.md`, `FaultKnowledge`, and `MarkdownKnowledgeLoader`. Topic IDs, guidance modes, priority, and canonical items in this document do not enter the runtime DTO.

## 3. Category Alignment

Final categories use `MV_SWITCHGEAR_10KV`, `IN_ROW_AC`, and `OM_TOOL`. Obsolete vocabulary category codes are documented only in the Vocabulary alignment table. Frozen canonical item names such as `ROW_AC_FAN` remain unchanged because category codes and procurement-object IDs are different layers.

| Domain | Final level-2 equipment categories |
|---|---|
| `POWER` | `MV_SWITCHGEAR_10KV`, `TRANSFORMER`, `LV_SWITCHGEAR_400V`, `UPS`, `HVDC`, `BATTERY` |
| `COOLING` | `CHILLER`, `SHU`, `COOLING_TOWER`, `COOLING_PUMP`, `WATER_SYSTEM`, `IN_ROW_AC` |
| `MONITORING_ENV` | `MONITORING`, `ROOM_ENVIRONMENT` |
| `ICT` | `TRANSMISSION`, `SERVER` |
| `OM` | `OM_TOOL` |

## 4. Knowledge Design Rules

- Equipment category identifies the faulty asset type; a Fault Topic identifies facts to confirm; canonical item identifies the standardized procurement object.
- A topic is neither an alarm code nor a diagnosis. Symptoms can produce a Candidate only after facts confirm the specific component itself is faulty and replacement is needed.
- Procurement aliases and Fault Knowledge aliases serve different recognition tasks and must not be copied mechanically.
- `FAULT_DRIVEN` still requires user, inspection, or Backend evidence. `CONDITIONAL` requires component-specific confirmation. `DIRECT_ONLY` requires an explicit purchase request or damage to that object itself.
- Quantity must come from `USER_CONFIRMED`, `USER_EXPLICIT_REQUEST`, or `BACKEND_FACT`; knowledge contains no default quantities.
- V1 excludes brand/model/part number/electrical or capacity specifications/interface/compatibility and all repair, disassembly, live-test, bypass, or reset steps.
- Risk is a simple future Markdown reference, not a Risk Engine. Professional personnel must handle high-risk work.
- P0 is frequent and relatively clear, P1 needs more confirmation, and P2 is infrequent/high-risk/specialist-dependent.

## 5. POWER

### MV_SWITCHGEAR_10KV

Covers 6 Vocabulary objects: `HV_CIRCUIT_BREAKER`, `HV_CONTACT`, `HV_PROTECTION_RELAY`, `HV_OPERATING_MECHANISM`, `HV_CURRENT_TRANSFORMER`, `HV_VOLTAGE_TRANSFORMER`. Confirmation boundaries, risk, and planned files are defined in the matrix.

### TRANSFORMER

Covers 5 Vocabulary objects: `TRANSFORMER_TEMP_CONTROLLER`, `TRANSFORMER_COOLING_FAN`, `TRANSFORMER_TEMP_SENSOR`, `TRANSFORMER_PROTECTION_DEVICE`, `TRANSFORMER_INSULATOR`. Confirmation boundaries, risk, and planned files are defined in the matrix.

### LV_SWITCHGEAR_400V

Covers 6 Vocabulary objects: `LV_CIRCUIT_BREAKER`, `LV_CONTACTOR`, `LV_POWER_METER`, `LV_CURRENT_TRANSFORMER`, `LV_SPD`, `LV_CONTROL_POWER_SUPPLY`. Confirmation boundaries, risk, and planned files are defined in the matrix.

### UPS

Covers 7 Vocabulary objects: `UPS_POWER_MODULE`, `UPS_RECTIFIER_MODULE`, `UPS_INVERTER_MODULE`, `UPS_STATIC_BYPASS_MODULE`, `UPS_CONTROL_BOARD`, `UPS_FAN`, `UPS_CAPACITOR`. Confirmation boundaries, risk, and planned files are defined in the matrix.

### HVDC

Covers 6 Vocabulary objects: `HVDC_RECTIFIER_MODULE`, `HVDC_MONITOR_MODULE`, `HVDC_DC_DISTRIBUTION_MODULE`, `HVDC_CONTROL_BOARD`, `HVDC_FAN`, `HVDC_BREAKER`. Confirmation boundaries, risk, and planned files are defined in the matrix.

### BATTERY

Covers 5 Vocabulary objects: `UPS_BATTERY`, `HVDC_BATTERY`, `BATTERY_MONITOR_MODULE`, `BATTERY_TEMP_SENSOR`, `BATTERY_CONNECTION_BAR`. Confirmation boundaries, risk, and planned files are defined in the matrix.

## 6. COOLING

### CHILLER

Covers 7 Vocabulary objects: `CHILLER_COMPRESSOR`, `CHILLER_CONTROL_BOARD`, `CHILLER_TEMP_SENSOR`, `CHILLER_PRESSURE_SENSOR`, `CHILLER_FLOW_SENSOR`, `CHILLER_FILTER`, `CHILLER_REFRIGERANT`. Confirmation boundaries, risk, and planned files are defined in the matrix.

### SHU

Covers 6 Vocabulary objects: `SHU_FAN`, `SHU_FAN_CONTROLLER`, `SHU_TEMP_SENSOR`, `SHU_HUMIDITY_SENSOR`, `SHU_CONTROL_BOARD`, `SHU_FILTER`. Confirmation boundaries, risk, and planned files are defined in the matrix.

### COOLING_TOWER

Covers 6 Vocabulary objects: `COOLING_TOWER_FAN`, `COOLING_TOWER_MOTOR`, `COOLING_TOWER_BELT`, `COOLING_TOWER_GEARBOX`, `COOLING_TOWER_FLOAT_VALVE`, `COOLING_TOWER_FILL`. Confirmation boundaries, risk, and planned files are defined in the matrix.

### COOLING_PUMP

Covers 6 Vocabulary objects: `PUMP_MOTOR`, `PUMP_BEARING`, `PUMP_MECHANICAL_SEAL`, `PUMP_IMPELLER`, `PUMP_COUPLING`, `PUMP_VFD`. Confirmation boundaries, risk, and planned files are defined in the matrix.

### WATER_SYSTEM

Covers 7 Vocabulary objects: `WATER_VALVE`, `WATER_ACTUATOR`, `WATER_FLOW_METER`, `WATER_PRESSURE_SENSOR`, `WATER_TEMP_SENSOR`, `WATER_LEAK_SENSOR`, `WATER_FILTER`. Confirmation boundaries, risk, and planned files are defined in the matrix.

### IN_ROW_AC

Covers 7 Vocabulary objects: `ROW_AC_FAN`, `ROW_AC_COMPRESSOR`, `ROW_AC_CONTROL_BOARD`, `ROW_AC_TEMP_SENSOR`, `ROW_AC_HUMIDITY_SENSOR`, `ROW_AC_FILTER`, `ROW_AC_EEV`. Confirmation boundaries, risk, and planned files are defined in the matrix.

## 7. MONITORING_ENV

### MONITORING

Covers 6 Vocabulary objects: `MONITORING_HOST`, `MONITORING_COLLECTOR`, `MONITORING_IO_MODULE`, `MONITORING_GATEWAY`, `MONITORING_DISPLAY`, `MONITORING_POWER_SUPPLY`. Confirmation boundaries, risk, and planned files are defined in the matrix.

### ROOM_ENVIRONMENT

Covers 5 Vocabulary objects: `ROOM_TEMP_HUMIDITY_SENSOR`, `ROOM_WATER_LEAK_SENSOR`, `ROOM_SMOKE_SENSOR`, `ROOM_DOOR_SENSOR`, `ROOM_AIR_QUALITY_SENSOR`. Confirmation boundaries, risk, and planned files are defined in the matrix.

## 8. ICT

### TRANSMISSION

Covers 6 Vocabulary objects: `OPTICAL_TRANSCEIVER`, `OPTICAL_FIBER`, `NETWORK_SWITCH`, `TRANSMISSION_BOARD`, `TRANSMISSION_POWER_MODULE`, `ODF_COMPONENT`. Confirmation boundaries, risk, and planned files are defined in the matrix.

### SERVER

Covers 9 Vocabulary objects: `SERVER_CPU`, `SERVER_MEMORY`, `SERVER_SSD`, `SERVER_HDD`, `SERVER_POWER_SUPPLY`, `SERVER_FAN`, `SERVER_RAID_CARD`, `SERVER_NIC`, `SERVER_GPU`. Confirmation boundaries, risk, and planned files are defined in the matrix.

## 9. OM

### OM_TOOL

Covers 8 Vocabulary objects: `MULTIMETER`, `CLAMP_METER`, `INSULATION_TESTER`, `THERMAL_CAMERA`, `NETWORK_TESTER`, `OPTICAL_POWER_METER`, `FIBER_FAULT_LOCATOR`, `PORTABLE_TEMP_HUMIDITY_METER`. Confirmation boundaries, risk, and planned files are defined in the matrix.

## 10. Knowledge Coverage Matrix

Every Vocabulary canonical item has at least one row. The additional `UPS_BATTERY_FAULT` row records the existing valid cross-category case. `REVIEW_REQUIRED` means the mapping boundary requires a data-center specialist; it is not an Agent conclusion.

| source_category | fault_topic_id | fault_topic | candidate_canonical_items | procurement_category | guidance_mode | minimum_confirmed_facts | risk_level | priority | planned_knowledge_file | status | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `MV_SWITCHGEAR_10KV` | `HV_CIRCUIT_BREAKER_FAULT` | 高压断路器 component fault | `HV_CIRCUIT_BREAKER` | `MV_SWITCHGEAR_10KV` | CONDITIONAL | Actual operating condition/external cause excluded; HV_CIRCUIT_BREAKER itself confirmed faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/mv-switchgear-10kv/hv-circuit-breaker-fault.md | REVIEW_REQUIRED | Data-center specialist must confirm mapping boundary |
| `MV_SWITCHGEAR_10KV` | `HV_CONTACT_FAULT` | 开关柜触头 component fault | `HV_CONTACT` | `MV_SWITCHGEAR_10KV` | CONDITIONAL | Actual operating condition/external cause excluded; HV_CONTACT itself confirmed faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/mv-switchgear-10kv/hv-contact-fault.md | REVIEW_REQUIRED | Data-center specialist must confirm mapping boundary |
| `MV_SWITCHGEAR_10KV` | `HV_PROTECTION_RELAY_FAULT` | 继电保护装置 component fault | `HV_PROTECTION_RELAY` | `MV_SWITCHGEAR_10KV` | CONDITIONAL | Actual operating condition/external cause excluded; HV_PROTECTION_RELAY itself confirmed faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/mv-switchgear-10kv/hv-protection-relay-fault.md | REVIEW_REQUIRED | Data-center specialist must confirm mapping boundary |
| `MV_SWITCHGEAR_10KV` | `HV_OPERATING_MECHANISM_FAULT` | 操作机构 component fault | `HV_OPERATING_MECHANISM` | `MV_SWITCHGEAR_10KV` | CONDITIONAL | Actual operating condition/external cause excluded; HV_OPERATING_MECHANISM itself confirmed faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/mv-switchgear-10kv/hv-operating-mechanism-fault.md | REVIEW_REQUIRED | Data-center specialist must confirm mapping boundary |
| `MV_SWITCHGEAR_10KV` | `HV_CURRENT_TRANSFORMER_FAULT` | 电流互感器 component fault | `HV_CURRENT_TRANSFORMER` | `MV_SWITCHGEAR_10KV` | CONDITIONAL | Actual operating condition/external cause excluded; HV_CURRENT_TRANSFORMER itself confirmed faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/mv-switchgear-10kv/hv-current-transformer-fault.md | REVIEW_REQUIRED | Data-center specialist must confirm mapping boundary |
| `MV_SWITCHGEAR_10KV` | `HV_VOLTAGE_TRANSFORMER_FAULT` | 电压互感器 component fault | `HV_VOLTAGE_TRANSFORMER` | `MV_SWITCHGEAR_10KV` | CONDITIONAL | Actual operating condition/external cause excluded; HV_VOLTAGE_TRANSFORMER itself confirmed faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/mv-switchgear-10kv/hv-voltage-transformer-fault.md | REVIEW_REQUIRED | Data-center specialist must confirm mapping boundary |
| `TRANSFORMER` | `TRANSFORMER_TEMP_CONTROLLER_FAULT` | 变压器温控器 component fault | `TRANSFORMER_TEMP_CONTROLLER` | `TRANSFORMER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms TRANSFORMER_TEMP_CONTROLLER itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/transformer/transformer-temp-controller-fault.md | PLANNED | — |
| `TRANSFORMER` | `TRANSFORMER_COOLING_FAN_FAULT` | 变压器冷却风机 component fault | `TRANSFORMER_COOLING_FAN` | `TRANSFORMER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms TRANSFORMER_COOLING_FAN itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/transformer/transformer-cooling-fan-fault.md | PLANNED | — |
| `TRANSFORMER` | `TRANSFORMER_TEMP_SENSOR_FAULT` | 变压器温度传感器 component fault | `TRANSFORMER_TEMP_SENSOR` | `TRANSFORMER` | CONDITIONAL | Actual operating condition/external cause excluded; TRANSFORMER_TEMP_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/transformer/transformer-temp-sensor-fault.md | PLANNED | — |
| `TRANSFORMER` | `TRANSFORMER_PROTECTION_DEVICE_FAULT` | 变压器保护装置 component fault | `TRANSFORMER_PROTECTION_DEVICE` | `TRANSFORMER` | CONDITIONAL | Actual operating condition/external cause excluded; TRANSFORMER_PROTECTION_DEVICE itself confirmed faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/transformer/transformer-protection-device-fault.md | REVIEW_REQUIRED | Data-center specialist must confirm mapping boundary |
| `TRANSFORMER` | `TRANSFORMER_INSULATOR_FAULT` | 变压器绝缘子 component fault | `TRANSFORMER_INSULATOR` | `TRANSFORMER` | CONDITIONAL | Actual operating condition/external cause excluded; TRANSFORMER_INSULATOR itself confirmed faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/transformer/transformer-insulator-fault.md | REVIEW_REQUIRED | Data-center specialist must confirm mapping boundary |
| `LV_SWITCHGEAR_400V` | `LV_CIRCUIT_BREAKER_FAULT` | 低压断路器 component fault | `LV_CIRCUIT_BREAKER` | `LV_SWITCHGEAR_400V` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms LV_CIRCUIT_BREAKER itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/lv-switchgear-400v/lv-circuit-breaker-fault.md | PLANNED | — |
| `LV_SWITCHGEAR_400V` | `LV_CONTACTOR_FAULT` | 交流接触器 component fault | `LV_CONTACTOR` | `LV_SWITCHGEAR_400V` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms LV_CONTACTOR itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/lv-switchgear-400v/lv-contactor-fault.md | PLANNED | — |
| `LV_SWITCHGEAR_400V` | `LV_POWER_METER_FAULT` | 电力仪表 component fault | `LV_POWER_METER` | `LV_SWITCHGEAR_400V` | CONDITIONAL | Actual operating condition/external cause excluded; LV_POWER_METER itself confirmed faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/lv-switchgear-400v/lv-power-meter-fault.md | PLANNED | — |
| `LV_SWITCHGEAR_400V` | `LV_CURRENT_TRANSFORMER_FAULT` | 低压电流互感器 component fault | `LV_CURRENT_TRANSFORMER` | `LV_SWITCHGEAR_400V` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms LV_CURRENT_TRANSFORMER itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/lv-switchgear-400v/lv-current-transformer-fault.md | PLANNED | — |
| `LV_SWITCHGEAR_400V` | `LV_SPD_FAULT` | 浪涌保护器 component fault | `LV_SPD` | `LV_SWITCHGEAR_400V` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms LV_SPD itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/lv-switchgear-400v/lv-spd-fault.md | PLANNED | — |
| `LV_SWITCHGEAR_400V` | `LV_CONTROL_POWER_SUPPLY_FAULT` | 控制电源 component fault | `LV_CONTROL_POWER_SUPPLY` | `LV_SWITCHGEAR_400V` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms LV_CONTROL_POWER_SUPPLY itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/lv-switchgear-400v/lv-control-power-supply-fault.md | PLANNED | — |
| `UPS` | `UPS_POWER_MODULE_FAULT` | UPS 功率模块 component fault | `UPS_POWER_MODULE` | `UPS` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms UPS_POWER_MODULE itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/ups/ups-power-module-fault.md | PLANNED | — |
| `UPS` | `UPS_RECTIFIER_MODULE_FAULT` | UPS 整流模块 component fault | `UPS_RECTIFIER_MODULE` | `UPS` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms UPS_RECTIFIER_MODULE itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/ups/ups-rectifier-module-fault.md | PLANNED | — |
| `UPS` | `UPS_INVERTER_MODULE_FAULT` | UPS 逆变模块 component fault | `UPS_INVERTER_MODULE` | `UPS` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms UPS_INVERTER_MODULE itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/ups/ups-inverter-module-fault.md | PLANNED | — |
| `UPS` | `UPS_STATIC_BYPASS_MODULE_FAULT` | UPS 静态旁路模块 component fault | `UPS_STATIC_BYPASS_MODULE` | `UPS` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms UPS_STATIC_BYPASS_MODULE itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/ups/ups-static-bypass-module-fault.md | PLANNED | — |
| `UPS` | `UPS_CONTROL_BOARD_FAULT` | UPS 控制板 component fault | `UPS_CONTROL_BOARD` | `UPS` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms UPS_CONTROL_BOARD itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/ups/ups-control-board-fault.md | PLANNED | — |
| `UPS` | `UPS_FAN_FAULT` | UPS 风扇 component fault | `UPS_FAN` | `UPS` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms UPS_FAN itself faulty and replacement needed; quantity confirmed | LOW | P0 | knowledge/fault-guidance/ups/ups-fan-fault.md | PLANNED | — |
| `UPS` | `UPS_CAPACITOR_FAULT` | UPS 电容 component fault | `UPS_CAPACITOR` | `UPS` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms UPS_CAPACITOR itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/ups/ups-capacitor-fault.md | PLANNED | — |
| `HVDC` | `HVDC_RECTIFIER_MODULE_FAULT` | 高压直流整流模块 component fault | `HVDC_RECTIFIER_MODULE` | `HVDC` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms HVDC_RECTIFIER_MODULE itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/hvdc/hvdc-rectifier-module-fault.md | PLANNED | — |
| `HVDC` | `HVDC_MONITOR_MODULE_FAULT` | 高压直流监控模块 component fault | `HVDC_MONITOR_MODULE` | `HVDC` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms HVDC_MONITOR_MODULE itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/hvdc/hvdc-monitor-module-fault.md | PLANNED | — |
| `HVDC` | `HVDC_DC_DISTRIBUTION_MODULE_FAULT` | 直流配电模块 component fault | `HVDC_DC_DISTRIBUTION_MODULE` | `HVDC` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms HVDC_DC_DISTRIBUTION_MODULE itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/hvdc/hvdc-dc-distribution-module-fault.md | PLANNED | — |
| `HVDC` | `HVDC_CONTROL_BOARD_FAULT` | 高压直流控制板 component fault | `HVDC_CONTROL_BOARD` | `HVDC` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms HVDC_CONTROL_BOARD itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/hvdc/hvdc-control-board-fault.md | PLANNED | — |
| `HVDC` | `HVDC_FAN_FAULT` | 高压直流风扇 component fault | `HVDC_FAN` | `HVDC` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms HVDC_FAN itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/hvdc/hvdc-fan-fault.md | PLANNED | — |
| `HVDC` | `HVDC_BREAKER_FAULT` | 直流断路器 component fault | `HVDC_BREAKER` | `HVDC` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms HVDC_BREAKER itself faulty and replacement needed; quantity confirmed | HIGH | P2 | knowledge/fault-guidance/hvdc/hvdc-breaker-fault.md | PLANNED | — |
| `BATTERY` | `BATTERY_UPS_BATTERY_FAULT` | UPS 蓄电池 component fault | `UPS_BATTERY` | `BATTERY` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms UPS_BATTERY itself faulty and replacement needed; quantity confirmed | LOW | P0 | knowledge/fault-guidance/battery/ups-battery-fault.md | PLANNED | — |
| `BATTERY` | `HVDC_BATTERY_FAULT` | 高压直流蓄电池 component fault | `HVDC_BATTERY` | `BATTERY` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms HVDC_BATTERY itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/battery/hvdc-battery-fault.md | PLANNED | — |
| `BATTERY` | `BATTERY_MONITOR_MODULE_FAULT` | 电池监测模块 component fault | `BATTERY_MONITOR_MODULE` | `BATTERY` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms BATTERY_MONITOR_MODULE itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/battery/battery-monitor-module-fault.md | PLANNED | — |
| `BATTERY` | `BATTERY_TEMP_SENSOR_FAULT` | 电池温度传感器 component fault | `BATTERY_TEMP_SENSOR` | `BATTERY` | CONDITIONAL | Actual operating condition/external cause excluded; BATTERY_TEMP_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/battery/battery-temp-sensor-fault.md | PLANNED | — |
| `BATTERY` | `BATTERY_CONNECTION_BAR_FAULT` | 电池连接件 component fault | `BATTERY_CONNECTION_BAR` | `BATTERY` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms BATTERY_CONNECTION_BAR itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/battery/battery-connection-bar-fault.md | PLANNED | — |
| `CHILLER` | `CHILLER_COMPRESSOR_FAULT` | 冷水机组压缩机 component fault | `CHILLER_COMPRESSOR` | `CHILLER` | CONDITIONAL | Actual operating condition/external cause excluded; CHILLER_COMPRESSOR itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P2 | knowledge/fault-guidance/chiller/chiller-compressor-fault.md | REVIEW_REQUIRED | Data-center specialist must confirm mapping boundary |
| `CHILLER` | `CHILLER_CONTROL_BOARD_FAULT` | 冷水机组控制板 component fault | `CHILLER_CONTROL_BOARD` | `CHILLER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms CHILLER_CONTROL_BOARD itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/chiller/chiller-control-board-fault.md | PLANNED | — |
| `CHILLER` | `CHILLER_TEMP_SENSOR_FAULT` | 冷水机组温度传感器 component fault | `CHILLER_TEMP_SENSOR` | `CHILLER` | CONDITIONAL | Actual operating condition/external cause excluded; CHILLER_TEMP_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/chiller/chiller-temp-sensor-fault.md | PLANNED | — |
| `CHILLER` | `CHILLER_PRESSURE_SENSOR_FAULT` | 冷水机组压力传感器 component fault | `CHILLER_PRESSURE_SENSOR` | `CHILLER` | CONDITIONAL | Actual operating condition/external cause excluded; CHILLER_PRESSURE_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/chiller/chiller-pressure-sensor-fault.md | PLANNED | — |
| `CHILLER` | `CHILLER_FLOW_SENSOR_FAULT` | 冷水机组流量传感器 component fault | `CHILLER_FLOW_SENSOR` | `CHILLER` | CONDITIONAL | Actual operating condition/external cause excluded; CHILLER_FLOW_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/chiller/chiller-flow-sensor-fault.md | PLANNED | — |
| `CHILLER` | `CHILLER_FILTER_FAULT` | 冷水机组过滤器 component fault | `CHILLER_FILTER` | `CHILLER` | CONDITIONAL | Actual operating condition/external cause excluded; CHILLER_FILTER itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/chiller/chiller-filter-fault.md | PLANNED | — |
| `CHILLER` | `CHILLER_REFRIGERANT_FAULT` | 制冷剂 component fault | `CHILLER_REFRIGERANT` | `CHILLER` | CONDITIONAL | Actual operating condition/external cause excluded; CHILLER_REFRIGERANT itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P2 | knowledge/fault-guidance/chiller/chiller-refrigerant-fault.md | REVIEW_REQUIRED | Data-center specialist must confirm mapping boundary |
| `SHU` | `SHU_FAN_FAULT` | SHU 风机 component fault | `SHU_FAN` | `SHU` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms SHU_FAN itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/shu/shu-fan-fault.md | PLANNED | — |
| `SHU` | `SHU_FAN_CONTROLLER_FAULT` | SHU 风机控制器 component fault | `SHU_FAN_CONTROLLER` | `SHU` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms SHU_FAN_CONTROLLER itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/shu/shu-fan-controller-fault.md | PLANNED | — |
| `SHU` | `SHU_TEMP_SENSOR_FAULT` | SHU 温度传感器 component fault | `SHU_TEMP_SENSOR` | `SHU` | CONDITIONAL | Actual operating condition/external cause excluded; SHU_TEMP_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/shu/shu-temp-sensor-fault.md | PLANNED | — |
| `SHU` | `SHU_HUMIDITY_SENSOR_FAULT` | SHU 湿度传感器 component fault | `SHU_HUMIDITY_SENSOR` | `SHU` | CONDITIONAL | Actual operating condition/external cause excluded; SHU_HUMIDITY_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/shu/shu-humidity-sensor-fault.md | PLANNED | — |
| `SHU` | `SHU_CONTROL_BOARD_FAULT` | SHU 控制板 component fault | `SHU_CONTROL_BOARD` | `SHU` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms SHU_CONTROL_BOARD itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/shu/shu-control-board-fault.md | PLANNED | — |
| `SHU` | `SHU_FILTER_FAULT` | SHU 过滤器 component fault | `SHU_FILTER` | `SHU` | CONDITIONAL | Actual operating condition/external cause excluded; SHU_FILTER itself confirmed faulty and replacement needed; quantity confirmed | LOW | P0 | knowledge/fault-guidance/shu/shu-filter-fault.md | PLANNED | — |
| `COOLING_TOWER` | `COOLING_TOWER_FAN_FAULT` | 冷却塔风机 component fault | `COOLING_TOWER_FAN` | `COOLING_TOWER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms COOLING_TOWER_FAN itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/cooling-tower/cooling-tower-fan-fault.md | PLANNED | — |
| `COOLING_TOWER` | `COOLING_TOWER_MOTOR_FAULT` | 冷却塔电机 component fault | `COOLING_TOWER_MOTOR` | `COOLING_TOWER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms COOLING_TOWER_MOTOR itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/cooling-tower/cooling-tower-motor-fault.md | PLANNED | — |
| `COOLING_TOWER` | `COOLING_TOWER_BELT_FAULT` | 冷却塔皮带 component fault | `COOLING_TOWER_BELT` | `COOLING_TOWER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms COOLING_TOWER_BELT itself faulty and replacement needed; quantity confirmed | MEDIUM | P0 | knowledge/fault-guidance/cooling-tower/cooling-tower-belt-fault.md | PLANNED | — |
| `COOLING_TOWER` | `COOLING_TOWER_GEARBOX_FAULT` | 冷却塔减速机 component fault | `COOLING_TOWER_GEARBOX` | `COOLING_TOWER` | CONDITIONAL | Actual operating condition/external cause excluded; COOLING_TOWER_GEARBOX itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P2 | knowledge/fault-guidance/cooling-tower/cooling-tower-gearbox-fault.md | REVIEW_REQUIRED | Data-center specialist must confirm mapping boundary |
| `COOLING_TOWER` | `COOLING_TOWER_FLOAT_VALVE_FAULT` | 冷却塔浮球阀 component fault | `COOLING_TOWER_FLOAT_VALVE` | `COOLING_TOWER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms COOLING_TOWER_FLOAT_VALVE itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/cooling-tower/cooling-tower-float-valve-fault.md | PLANNED | — |
| `COOLING_TOWER` | `COOLING_TOWER_FILL_FAULT` | 冷却塔填料 component fault | `COOLING_TOWER_FILL` | `COOLING_TOWER` | CONDITIONAL | Actual operating condition/external cause excluded; COOLING_TOWER_FILL itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/cooling-tower/cooling-tower-fill-fault.md | PLANNED | — |
| `COOLING_PUMP` | `PUMP_MOTOR_FAULT` | 水泵电机 component fault | `PUMP_MOTOR` | `COOLING_PUMP` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms PUMP_MOTOR itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/cooling-pump/pump-motor-fault.md | PLANNED | — |
| `COOLING_PUMP` | `PUMP_BEARING_FAULT` | 水泵轴承 component fault | `PUMP_BEARING` | `COOLING_PUMP` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms PUMP_BEARING itself faulty and replacement needed; quantity confirmed | MEDIUM | P0 | knowledge/fault-guidance/cooling-pump/pump-bearing-fault.md | PLANNED | — |
| `COOLING_PUMP` | `PUMP_MECHANICAL_SEAL_FAULT` | 水泵机械密封 component fault | `PUMP_MECHANICAL_SEAL` | `COOLING_PUMP` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms PUMP_MECHANICAL_SEAL itself faulty and replacement needed; quantity confirmed | MEDIUM | P0 | knowledge/fault-guidance/cooling-pump/pump-mechanical-seal-fault.md | PLANNED | — |
| `COOLING_PUMP` | `PUMP_IMPELLER_FAULT` | 水泵叶轮 component fault | `PUMP_IMPELLER` | `COOLING_PUMP` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms PUMP_IMPELLER itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/cooling-pump/pump-impeller-fault.md | PLANNED | — |
| `COOLING_PUMP` | `PUMP_COUPLING_FAULT` | 水泵联轴器 component fault | `PUMP_COUPLING` | `COOLING_PUMP` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms PUMP_COUPLING itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/cooling-pump/pump-coupling-fault.md | PLANNED | — |
| `COOLING_PUMP` | `PUMP_VFD_FAULT` | 水泵变频器 component fault | `PUMP_VFD` | `COOLING_PUMP` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms PUMP_VFD itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/cooling-pump/pump-vfd-fault.md | PLANNED | — |
| `WATER_SYSTEM` | `WATER_VALVE_FAULT` | 水系统阀门 component fault | `WATER_VALVE` | `WATER_SYSTEM` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms WATER_VALVE itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/water-system/water-valve-fault.md | PLANNED | — |
| `WATER_SYSTEM` | `WATER_ACTUATOR_FAULT` | 阀门执行器 component fault | `WATER_ACTUATOR` | `WATER_SYSTEM` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms WATER_ACTUATOR itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/water-system/water-actuator-fault.md | PLANNED | — |
| `WATER_SYSTEM` | `WATER_FLOW_METER_FAULT` | 流量计 component fault | `WATER_FLOW_METER` | `WATER_SYSTEM` | CONDITIONAL | Actual operating condition/external cause excluded; WATER_FLOW_METER itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/water-system/water-flow-meter-fault.md | PLANNED | — |
| `WATER_SYSTEM` | `WATER_PRESSURE_SENSOR_FAULT` | 水压传感器 component fault | `WATER_PRESSURE_SENSOR` | `WATER_SYSTEM` | CONDITIONAL | Actual operating condition/external cause excluded; WATER_PRESSURE_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/water-system/water-pressure-sensor-fault.md | PLANNED | — |
| `WATER_SYSTEM` | `WATER_TEMP_SENSOR_FAULT` | 水温传感器 component fault | `WATER_TEMP_SENSOR` | `WATER_SYSTEM` | CONDITIONAL | Actual operating condition/external cause excluded; WATER_TEMP_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/water-system/water-temp-sensor-fault.md | PLANNED | — |
| `WATER_SYSTEM` | `WATER_LEAK_SENSOR_FAULT` | 漏水传感器 component fault | `WATER_LEAK_SENSOR` | `WATER_SYSTEM` | CONDITIONAL | Actual operating condition/external cause excluded; WATER_LEAK_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/water-system/water-leak-sensor-fault.md | PLANNED | — |
| `WATER_SYSTEM` | `WATER_FILTER_FAULT` | 水系统过滤器 component fault | `WATER_FILTER` | `WATER_SYSTEM` | CONDITIONAL | Actual operating condition/external cause excluded; WATER_FILTER itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/water-system/water-filter-fault.md | PLANNED | — |
| `IN_ROW_AC` | `ROW_AC_FAN_FAULT` | 列间空调风机 component fault | `ROW_AC_FAN` | `IN_ROW_AC` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms ROW_AC_FAN itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/in-row-ac/row-ac-fan-fault.md | PLANNED | — |
| `IN_ROW_AC` | `ROW_AC_COMPRESSOR_FAULT` | 列间空调压缩机 component fault | `ROW_AC_COMPRESSOR` | `IN_ROW_AC` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms ROW_AC_COMPRESSOR itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/in-row-ac/row-ac-compressor-fault.md | PLANNED | — |
| `IN_ROW_AC` | `ROW_AC_CONTROL_BOARD_FAULT` | 列间空调控制板 component fault | `ROW_AC_CONTROL_BOARD` | `IN_ROW_AC` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms ROW_AC_CONTROL_BOARD itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/in-row-ac/row-ac-control-board-fault.md | PLANNED | — |
| `IN_ROW_AC` | `ROW_AC_TEMP_SENSOR_FAULT` | 列间空调温度传感器 component fault | `ROW_AC_TEMP_SENSOR` | `IN_ROW_AC` | CONDITIONAL | Actual operating condition/external cause excluded; ROW_AC_TEMP_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/in-row-ac/row-ac-temp-sensor-fault.md | PLANNED | — |
| `IN_ROW_AC` | `ROW_AC_HUMIDITY_SENSOR_FAULT` | 列间空调湿度传感器 component fault | `ROW_AC_HUMIDITY_SENSOR` | `IN_ROW_AC` | CONDITIONAL | Actual operating condition/external cause excluded; ROW_AC_HUMIDITY_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/in-row-ac/row-ac-humidity-sensor-fault.md | PLANNED | — |
| `IN_ROW_AC` | `ROW_AC_FILTER_FAULT` | 列间空调滤网 component fault | `ROW_AC_FILTER` | `IN_ROW_AC` | CONDITIONAL | Actual operating condition/external cause excluded; ROW_AC_FILTER itself confirmed faulty and replacement needed; quantity confirmed | MEDIUM | P0 | knowledge/fault-guidance/in-row-ac/row-ac-filter-fault.md | PLANNED | — |
| `IN_ROW_AC` | `ROW_AC_EEV_FAULT` | 电子膨胀阀 component fault | `ROW_AC_EEV` | `IN_ROW_AC` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms ROW_AC_EEV itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/in-row-ac/row-ac-eev-fault.md | PLANNED | — |
| `MONITORING` | `MONITORING_HOST_FAULT` | 动环监控主机 component fault | `MONITORING_HOST` | `MONITORING` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms MONITORING_HOST itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/monitoring/monitoring-host-fault.md | PLANNED | — |
| `MONITORING` | `MONITORING_COLLECTOR_FAULT` | 数据采集器 component fault | `MONITORING_COLLECTOR` | `MONITORING` | CONDITIONAL | Actual operating condition/external cause excluded; MONITORING_COLLECTOR itself confirmed faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/monitoring/monitoring-collector-fault.md | PLANNED | — |
| `MONITORING` | `MONITORING_IO_MODULE_FAULT` | IO 模块 component fault | `MONITORING_IO_MODULE` | `MONITORING` | CONDITIONAL | Actual operating condition/external cause excluded; MONITORING_IO_MODULE itself confirmed faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/monitoring/monitoring-io-module-fault.md | PLANNED | — |
| `MONITORING` | `MONITORING_GATEWAY_FAULT` | 监控网关 component fault | `MONITORING_GATEWAY` | `MONITORING` | CONDITIONAL | Actual operating condition/external cause excluded; MONITORING_GATEWAY itself confirmed faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/monitoring/monitoring-gateway-fault.md | PLANNED | — |
| `MONITORING` | `MONITORING_DISPLAY_FAULT` | 监控显示终端 component fault | `MONITORING_DISPLAY` | `MONITORING` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms MONITORING_DISPLAY itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/monitoring/monitoring-display-fault.md | PLANNED | — |
| `MONITORING` | `MONITORING_POWER_SUPPLY_FAULT` | 监控电源模块 component fault | `MONITORING_POWER_SUPPLY` | `MONITORING` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms MONITORING_POWER_SUPPLY itself faulty and replacement needed; quantity confirmed | MEDIUM | P0 | knowledge/fault-guidance/monitoring/monitoring-power-supply-fault.md | PLANNED | — |
| `ROOM_ENVIRONMENT` | `ROOM_TEMP_HUMIDITY_SENSOR_FAULT` | 温湿度传感器 component fault | `ROOM_TEMP_HUMIDITY_SENSOR` | `ROOM_ENVIRONMENT` | CONDITIONAL | Actual operating condition/external cause excluded; ROOM_TEMP_HUMIDITY_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | LOW | P0 | knowledge/fault-guidance/room-environment/room-temp-humidity-sensor-fault.md | PLANNED | — |
| `ROOM_ENVIRONMENT` | `ROOM_WATER_LEAK_SENSOR_FAULT` | 漏水传感器 component fault | `ROOM_WATER_LEAK_SENSOR` | `ROOM_ENVIRONMENT` | CONDITIONAL | Actual operating condition/external cause excluded; ROOM_WATER_LEAK_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/room-environment/room-water-leak-sensor-fault.md | PLANNED | — |
| `ROOM_ENVIRONMENT` | `ROOM_SMOKE_SENSOR_FAULT` | 烟雾传感器 component fault | `ROOM_SMOKE_SENSOR` | `ROOM_ENVIRONMENT` | CONDITIONAL | Actual operating condition/external cause excluded; ROOM_SMOKE_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/room-environment/room-smoke-sensor-fault.md | PLANNED | — |
| `ROOM_ENVIRONMENT` | `ROOM_DOOR_SENSOR_FAULT` | 门磁传感器 component fault | `ROOM_DOOR_SENSOR` | `ROOM_ENVIRONMENT` | CONDITIONAL | Actual operating condition/external cause excluded; ROOM_DOOR_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/room-environment/room-door-sensor-fault.md | PLANNED | — |
| `ROOM_ENVIRONMENT` | `ROOM_AIR_QUALITY_SENSOR_FAULT` | 空气质量传感器 component fault | `ROOM_AIR_QUALITY_SENSOR` | `ROOM_ENVIRONMENT` | CONDITIONAL | Actual operating condition/external cause excluded; ROOM_AIR_QUALITY_SENSOR itself confirmed faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/room-environment/room-air-quality-sensor-fault.md | PLANNED | — |
| `TRANSMISSION` | `OPTICAL_TRANSCEIVER_FAULT` | 光模块 component fault | `OPTICAL_TRANSCEIVER` | `TRANSMISSION` | CONDITIONAL | Actual operating condition/external cause excluded; OPTICAL_TRANSCEIVER itself confirmed faulty and replacement needed; quantity confirmed | LOW | P0 | knowledge/fault-guidance/transmission/optical-transceiver-fault.md | PLANNED | — |
| `TRANSMISSION` | `OPTICAL_FIBER_FAULT` | 光纤跳线 component fault | `OPTICAL_FIBER` | `TRANSMISSION` | CONDITIONAL | Actual operating condition/external cause excluded; OPTICAL_FIBER itself confirmed faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/transmission/optical-fiber-fault.md | PLANNED | — |
| `TRANSMISSION` | `NETWORK_SWITCH_FAULT` | 网络交换机 component fault | `NETWORK_SWITCH` | `TRANSMISSION` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms NETWORK_SWITCH itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/transmission/network-switch-fault.md | PLANNED | — |
| `TRANSMISSION` | `TRANSMISSION_BOARD_FAULT` | 传输业务板卡 component fault | `TRANSMISSION_BOARD` | `TRANSMISSION` | CONDITIONAL | Actual operating condition/external cause excluded; TRANSMISSION_BOARD itself confirmed faulty and replacement needed; quantity confirmed | LOW | P2 | knowledge/fault-guidance/transmission/transmission-board-fault.md | REVIEW_REQUIRED | Data-center specialist must confirm mapping boundary |
| `TRANSMISSION` | `TRANSMISSION_POWER_MODULE_FAULT` | 传输设备电源模块 component fault | `TRANSMISSION_POWER_MODULE` | `TRANSMISSION` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms TRANSMISSION_POWER_MODULE itself faulty and replacement needed; quantity confirmed | MEDIUM | P1 | knowledge/fault-guidance/transmission/transmission-power-module-fault.md | PLANNED | — |
| `TRANSMISSION` | `ODF_COMPONENT_FAULT` | ODF 配线组件 component fault | `ODF_COMPONENT` | `TRANSMISSION` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms ODF_COMPONENT itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/transmission/odf-component-fault.md | PLANNED | — |
| `SERVER` | `SERVER_CPU_FAULT` | 服务器 CPU component fault | `SERVER_CPU` | `SERVER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms SERVER_CPU itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/server/server-cpu-fault.md | PLANNED | — |
| `SERVER` | `SERVER_MEMORY_FAULT` | 服务器内存 component fault | `SERVER_MEMORY` | `SERVER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms SERVER_MEMORY itself faulty and replacement needed; quantity confirmed | LOW | P0 | knowledge/fault-guidance/server/server-memory-fault.md | PLANNED | — |
| `SERVER` | `SERVER_SSD_FAULT` | 服务器 SSD component fault | `SERVER_SSD` | `SERVER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms SERVER_SSD itself faulty and replacement needed; quantity confirmed | LOW | P0 | knowledge/fault-guidance/server/server-ssd-fault.md | PLANNED | — |
| `SERVER` | `SERVER_HDD_FAULT` | 服务器 HDD component fault | `SERVER_HDD` | `SERVER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms SERVER_HDD itself faulty and replacement needed; quantity confirmed | LOW | P0 | knowledge/fault-guidance/server/server-hdd-fault.md | PLANNED | — |
| `SERVER` | `SERVER_POWER_SUPPLY_FAULT` | 服务器电源 component fault | `SERVER_POWER_SUPPLY` | `SERVER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms SERVER_POWER_SUPPLY itself faulty and replacement needed; quantity confirmed | MEDIUM | P0 | knowledge/fault-guidance/server/server-power-supply-fault.md | PLANNED | — |
| `SERVER` | `SERVER_FAN_FAULT` | 服务器风扇 component fault | `SERVER_FAN` | `SERVER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms SERVER_FAN itself faulty and replacement needed; quantity confirmed | LOW | P0 | knowledge/fault-guidance/server/server-fan-fault.md | PLANNED | — |
| `SERVER` | `SERVER_RAID_CARD_FAULT` | RAID 卡 component fault | `SERVER_RAID_CARD` | `SERVER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms SERVER_RAID_CARD itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/server/server-raid-card-fault.md | PLANNED | — |
| `SERVER` | `SERVER_NIC_FAULT` | 服务器网卡 component fault | `SERVER_NIC` | `SERVER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms SERVER_NIC itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/server/server-nic-fault.md | PLANNED | — |
| `SERVER` | `SERVER_GPU_FAULT` | GPU 加速卡 component fault | `SERVER_GPU` | `SERVER` | FAULT_DRIVEN | Inspection, user, or Backend fact confirms SERVER_GPU itself faulty and replacement needed; quantity confirmed | LOW | P1 | knowledge/fault-guidance/server/server-gpu-fault.md | PLANNED | — |
| `OM_TOOL` | `MULTIMETER_DIRECT_REPLACEMENT` | 数字万用表 component fault | `MULTIMETER` | `OM_TOOL` | DIRECT_ONLY | Explicit user request or confirmed tool damage requiring replacement; quantity confirmed | LOW | P2 | knowledge/fault-guidance/om-tool/multimeter-direct-replacement.md | PLANNED | — |
| `OM_TOOL` | `CLAMP_METER_DIRECT_REPLACEMENT` | 钳形电流表 component fault | `CLAMP_METER` | `OM_TOOL` | DIRECT_ONLY | Explicit user request or confirmed tool damage requiring replacement; quantity confirmed | LOW | P2 | knowledge/fault-guidance/om-tool/clamp-meter-direct-replacement.md | PLANNED | — |
| `OM_TOOL` | `INSULATION_TESTER_DIRECT_REPLACEMENT` | 绝缘电阻测试仪 component fault | `INSULATION_TESTER` | `OM_TOOL` | DIRECT_ONLY | Explicit user request or confirmed tool damage requiring replacement; quantity confirmed | LOW | P2 | knowledge/fault-guidance/om-tool/insulation-tester-direct-replacement.md | PLANNED | — |
| `OM_TOOL` | `THERMAL_CAMERA_DIRECT_REPLACEMENT` | 红外热像仪 component fault | `THERMAL_CAMERA` | `OM_TOOL` | DIRECT_ONLY | Explicit user request or confirmed tool damage requiring replacement; quantity confirmed | LOW | P2 | knowledge/fault-guidance/om-tool/thermal-camera-direct-replacement.md | PLANNED | — |
| `OM_TOOL` | `NETWORK_TESTER_DIRECT_REPLACEMENT` | 网络测试仪 component fault | `NETWORK_TESTER` | `OM_TOOL` | DIRECT_ONLY | Explicit user request or confirmed tool damage requiring replacement; quantity confirmed | LOW | P2 | knowledge/fault-guidance/om-tool/network-tester-direct-replacement.md | PLANNED | — |
| `OM_TOOL` | `OPTICAL_POWER_METER_DIRECT_REPLACEMENT` | 光功率计 component fault | `OPTICAL_POWER_METER` | `OM_TOOL` | DIRECT_ONLY | Explicit user request or confirmed tool damage requiring replacement; quantity confirmed | LOW | P2 | knowledge/fault-guidance/om-tool/optical-power-meter-direct-replacement.md | PLANNED | — |
| `OM_TOOL` | `FIBER_FAULT_LOCATOR_DIRECT_REPLACEMENT` | 红光笔 component fault | `FIBER_FAULT_LOCATOR` | `OM_TOOL` | DIRECT_ONLY | Explicit user request or confirmed tool damage requiring replacement; quantity confirmed | LOW | P2 | knowledge/fault-guidance/om-tool/fiber-fault-locator-direct-replacement.md | PLANNED | — |
| `OM_TOOL` | `PORTABLE_TEMP_HUMIDITY_METER_DIRECT_REPLACEMENT` | 便携式温湿度仪 component fault | `PORTABLE_TEMP_HUMIDITY_METER` | `OM_TOOL` | DIRECT_ONLY | Explicit user request or confirmed tool damage requiring replacement; quantity confirmed | LOW | P2 | knowledge/fault-guidance/om-tool/portable-temp-humidity-meter-direct-replacement.md | PLANNED | — |
| `UPS` | `UPS_BATTERY_FAULT` | UPS battery abnormality / BATTERY FAULT | `UPS_BATTERY` | `BATTERY` | FAULT_DRIVEN | Battery inspection completed; faulty batteries confirmed to require replacement; quantity confirmed | MEDIUM | P0 | knowledge/fault-guidance/ups/ups-battery-fault.md | EXISTING | Valid cross-category source/procurement mapping |

## 11. Priority

- P0 topics: 16
- P1 topics: 58
- P2 topics: 35
- Priority controls future authoring order only; it never relaxes evidence or safety requirements.

## 12. V1 Boundaries

- Matrix topics: 109; FAULT_DRIVEN 60, CONDITIONAL 41, DIRECT_ONLY 8.
- REVIEW_REQUIRED: 12; these require specialist review.
- Existing Knowledge: 1; future planned/review files: 108.
- No new canonical items, Runtime DTO/Search/Orchestrator changes, database tables, compatibility knowledge, repair steps, or Task08 implementation.
