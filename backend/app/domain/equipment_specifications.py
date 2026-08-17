"""Recommended stable specification keys; values are optional and never diagnostic rules."""

RECOMMENDED_SPECIFICATION_KEYS: dict[str, frozenset[str]] = {
    "MV_SWITCHGEAR_10KV": frozenset(
        {"rated_voltage_kv", "rated_current_a", "short_circuit_rating_ka", "cabinet_type"}
    ),
    "TRANSFORMER": frozenset(
        {
            "rated_capacity_kva",
            "high_voltage_kv",
            "low_voltage_v",
            "cooling_method",
            "insulation_type",
        }
    ),
    "LV_SWITCHGEAR_400V": frozenset(
        {"rated_voltage_v", "rated_current_a", "short_circuit_rating_ka", "cabinet_type"}
    ),
    "UPS": frozenset(
        {
            "capacity_kva",
            "rated_power_kw",
            "input_voltage_v",
            "output_voltage_v",
            "topology",
            "modular",
            "module_power_kw",
        }
    ),
    "HVDC": frozenset({"rated_power_kw", "input_voltage_v", "output_voltage_v", "module_count"}),
    "BATTERY": frozenset(
        {"chemistry", "nominal_voltage_v", "capacity_ah", "unit_count", "battery_form"}
    ),
    "MONITORING": frozenset({"system_type", "protocol", "interface", "channel_count"}),
    "CHILLER": frozenset(
        {"cooling_capacity_kw", "compressor_type", "refrigerant", "rated_power_kw"}
    ),
    "SHU": frozenset(),
    "COOLING_TOWER": frozenset({"cooling_capacity_kw", "water_flow_m3h", "fan_power_kw"}),
    "COOLING_PUMP": frozenset({"flow_m3h", "head_m", "motor_power_kw", "rated_voltage_v"}),
    "ROOM_ENVIRONMENT": frozenset({"device_type", "measurement_range", "interface", "protocol"}),
    "WATER_SYSTEM": frozenset({"system_type", "design_flow_m3h", "design_pressure_mpa"}),
    "TRANSMISSION": frozenset({"device_type", "data_rate_gbps", "interface_type", "protocol"}),
    "SERVER": frozenset(
        {
            "form_factor",
            "cpu_model",
            "cpu_count",
            "memory_gb",
            "storage_type",
            "storage_capacity_tb",
            "gpu_model",
            "nic_speed_gbps",
            "psu_power_w",
        }
    ),
    "OM_TOOL": frozenset(
        {"tool_type", "measurement_range", "accuracy_class", "calibration_cycle_months"}
    ),
    "IN_ROW_AC": frozenset(
        {"cooling_capacity_kw", "airflow_m3h", "cooling_type", "rated_power_kw"}
    ),
}

FORBIDDEN_RUNTIME_KEYS = frozenset(
    {
        "current_load",
        "current_temperature",
        "current_alarm",
        "fault_status",
        "last_maintenance_time",
    }
)
