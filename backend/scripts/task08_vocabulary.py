"""Seed-only machine-readable form of Task07 Procurement Vocabulary v1."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VocabularyItem:
    canonical_item: str
    display_name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class VocabularyCategory:
    category_code: str
    database_category_code: str
    display_name: str
    items: tuple[VocabularyItem, ...]


def _item(code: str, name: str, aliases: str) -> VocabularyItem:
    return VocabularyItem(code, name, tuple(part.strip() for part in aliases.split("、")))


VOCABULARY = (
    VocabularyCategory(
        "HV_SWITCHGEAR_10KV",
        "MV_SWITCHGEAR_10KV",
        "10kV开关柜",
        (
            _item("HV_CIRCUIT_BREAKER", "高压断路器", "真空断路器、10kV断路器、高压开关"),
            _item("HV_CONTACT", "开关柜触头", "梅花触头、动触头、静触头、高压触头"),
            _item("HV_PROTECTION_RELAY", "继电保护装置", "保护继电器、微机保护、综保装置"),
            _item("HV_OPERATING_MECHANISM", "操作机构", "断路器操作机构、储能机构"),
            _item("HV_CURRENT_TRANSFORMER", "电流互感器", "CT、电流互感器、高压CT"),
            _item("HV_VOLTAGE_TRANSFORMER", "电压互感器", "PT、电压互感器、高压PT"),
        ),
    ),
    VocabularyCategory(
        "TRANSFORMER",
        "TRANSFORMER",
        "变压器",
        (
            _item(
                "TRANSFORMER_TEMP_CONTROLLER", "变压器温控器", "温度控制器、变压器温控仪、温控仪"
            ),
            _item("TRANSFORMER_COOLING_FAN", "变压器冷却风机", "变压器风机、散热风机、冷却风扇"),
            _item("TRANSFORMER_TEMP_SENSOR", "变压器温度传感器", "温度探头、测温探头、温度传感器"),
            _item("TRANSFORMER_PROTECTION_DEVICE", "变压器保护装置", "变压器保护器、保护继电器"),
            _item("TRANSFORMER_INSULATOR", "变压器绝缘子", "支柱绝缘子、绝缘组件"),
        ),
    ),
    VocabularyCategory(
        "LV_SWITCHGEAR_400V",
        "LV_SWITCHGEAR_400V",
        "400V配电柜",
        (
            _item("LV_CIRCUIT_BREAKER", "低压断路器", "塑壳断路器、框架断路器、空气开关"),
            _item("LV_CONTACTOR", "交流接触器", "接触器、低压接触器"),
            _item("LV_POWER_METER", "电力仪表", "多功能电表、电力监测仪、电能表"),
            _item("LV_CURRENT_TRANSFORMER", "低压电流互感器", "CT、电流互感器"),
            _item("LV_SPD", "浪涌保护器", "SPD、防雷器、电涌保护器"),
            _item("LV_CONTROL_POWER_SUPPLY", "控制电源", "开关电源、辅助电源、电源模块"),
        ),
    ),
    VocabularyCategory(
        "UPS",
        "UPS",
        "UPS",
        (
            _item("UPS_POWER_MODULE", "UPS 功率模块", "功率模块、UPS模块、电源模块"),
            _item("UPS_RECTIFIER_MODULE", "UPS 整流模块", "整流器、整流模块"),
            _item("UPS_INVERTER_MODULE", "UPS 逆变模块", "逆变器、逆变模块"),
            _item("UPS_STATIC_BYPASS_MODULE", "UPS 静态旁路模块", "静态开关、旁路模块、STS模块"),
            _item("UPS_CONTROL_BOARD", "UPS 控制板", "主控板、控制板、UPS主板"),
            _item("UPS_FAN", "UPS 风扇", "UPS风机、散热风扇、冷却风扇"),
            _item("UPS_CAPACITOR", "UPS 电容", "直流电容、交流电容、滤波电容"),
        ),
    ),
    VocabularyCategory(
        "HVDC",
        "HVDC",
        "高压直流",
        (
            _item("HVDC_RECTIFIER_MODULE", "高压直流整流模块", "整流模块、整流器模块"),
            _item("HVDC_MONITOR_MODULE", "高压直流监控模块", "监控模块、监控单元"),
            _item("HVDC_DC_DISTRIBUTION_MODULE", "直流配电模块", "输出配电模块、直流分配模块"),
            _item("HVDC_CONTROL_BOARD", "高压直流控制板", "主控板、控制板"),
            _item("HVDC_FAN", "高压直流风扇", "散热风扇、冷却风扇"),
            _item("HVDC_BREAKER", "直流断路器", "DC断路器、直流空开"),
        ),
    ),
    VocabularyCategory(
        "BATTERY",
        "BATTERY",
        "蓄电池",
        (
            _item("UPS_BATTERY", "UPS 蓄电池", "UPS电池、UPS蓄电池、电池组、蓄电池组"),
            _item("HVDC_BATTERY", "高压直流蓄电池", "直流系统电池、高压直流电池"),
            _item("BATTERY_MONITOR_MODULE", "电池监测模块", "单体监测模块、电池监控模块"),
            _item("BATTERY_TEMP_SENSOR", "电池温度传感器", "电池温度探头、测温探头"),
            _item("BATTERY_CONNECTION_BAR", "电池连接件", "电池连接条、连接铜排、电池连接片"),
        ),
    ),
    VocabularyCategory(
        "CHILLER",
        "CHILLER",
        "冷水机组",
        (
            _item("CHILLER_COMPRESSOR", "冷水机组压缩机", "压缩机、冷机压缩机"),
            _item("CHILLER_CONTROL_BOARD", "冷水机组控制板", "主控板、控制器、冷机控制板"),
            _item("CHILLER_TEMP_SENSOR", "冷水机组温度传感器", "温度探头、冷机温度传感器"),
            _item("CHILLER_PRESSURE_SENSOR", "冷水机组压力传感器", "压力探头、压力变送器"),
            _item("CHILLER_FLOW_SENSOR", "冷水机组流量传感器", "流量计、流量开关"),
            _item("CHILLER_FILTER", "冷水机组过滤器", "过滤器、滤芯"),
            _item("CHILLER_REFRIGERANT", "制冷剂", "冷媒、雪种"),
        ),
    ),
    VocabularyCategory(
        "SHU",
        "SHU",
        "SHU",
        (
            _item("SHU_FAN", "SHU 风机", "SHU风扇、送风风机、EC风机"),
            _item("SHU_FAN_CONTROLLER", "SHU 风机控制器", "风机控制器、EC风机控制模块"),
            _item("SHU_TEMP_SENSOR", "SHU 温度传感器", "温度探头、送风温度传感器"),
            _item("SHU_HUMIDITY_SENSOR", "SHU 湿度传感器", "湿度探头、温湿度传感器"),
            _item("SHU_CONTROL_BOARD", "SHU 控制板", "主控板、控制器"),
            _item("SHU_FILTER", "SHU 过滤器", "空气过滤器、滤网"),
        ),
    ),
    VocabularyCategory(
        "COOLING_TOWER",
        "COOLING_TOWER",
        "冷却塔",
        (
            _item("COOLING_TOWER_FAN", "冷却塔风机", "塔风机、冷却塔风扇"),
            _item("COOLING_TOWER_MOTOR", "冷却塔电机", "风机电机、塔电机"),
            _item("COOLING_TOWER_BELT", "冷却塔皮带", "风机皮带、传动皮带"),
            _item("COOLING_TOWER_GEARBOX", "冷却塔减速机", "减速箱、齿轮箱"),
            _item("COOLING_TOWER_FLOAT_VALVE", "冷却塔浮球阀", "补水浮球阀、浮球"),
            _item("COOLING_TOWER_FILL", "冷却塔填料", "冷却填料、散热填料"),
        ),
    ),
    VocabularyCategory(
        "COOLING_PUMP",
        "COOLING_PUMP",
        "冷却泵",
        (
            _item("PUMP_MOTOR", "水泵电机", "冷却泵电机、泵电机"),
            _item("PUMP_BEARING", "水泵轴承", "冷却泵轴承、泵轴承"),
            _item("PUMP_MECHANICAL_SEAL", "水泵机械密封", "机械密封、机封、泵密封"),
            _item("PUMP_IMPELLER", "水泵叶轮", "冷却泵叶轮、泵叶轮"),
            _item("PUMP_COUPLING", "水泵联轴器", "联轴器、泵联轴器"),
            _item("PUMP_VFD", "水泵变频器", "变频器、泵变频器、VFD"),
        ),
    ),
    VocabularyCategory(
        "WATER_SYSTEM",
        "WATER_SYSTEM",
        "水系统",
        (
            _item("WATER_VALVE", "水系统阀门", "电动阀、调节阀、截止阀、蝶阀"),
            _item("WATER_ACTUATOR", "阀门执行器", "电动执行器、阀门电机"),
            _item("WATER_FLOW_METER", "流量计", "水流量计、流量传感器"),
            _item("WATER_PRESSURE_SENSOR", "水压传感器", "压力传感器、压力变送器"),
            _item("WATER_TEMP_SENSOR", "水温传感器", "水温探头、温度传感器"),
            _item("WATER_LEAK_SENSOR", "漏水传感器", "漏水检测器、漏水探测器"),
            _item("WATER_FILTER", "水系统过滤器", "Y型过滤器、过滤器、滤芯"),
        ),
    ),
    VocabularyCategory(
        "ROW_AC",
        "IN_ROW_AC",
        "列间空调",
        (
            _item("ROW_AC_FAN", "列间空调风机", "EC风机、空调风扇、送风风机"),
            _item("ROW_AC_COMPRESSOR", "列间空调压缩机", "空调压缩机、压缩机"),
            _item("ROW_AC_CONTROL_BOARD", "列间空调控制板", "主控板、空调控制器"),
            _item("ROW_AC_TEMP_SENSOR", "列间空调温度传感器", "温度探头、送风温度传感器"),
            _item("ROW_AC_HUMIDITY_SENSOR", "列间空调湿度传感器", "湿度探头、温湿度传感器"),
            _item("ROW_AC_FILTER", "列间空调滤网", "空气滤网、过滤器"),
            _item("ROW_AC_EEV", "电子膨胀阀", "EEV、膨胀阀"),
        ),
    ),
    VocabularyCategory(
        "MONITORING",
        "MONITORING",
        "监控",
        (
            _item("MONITORING_HOST", "动环监控主机", "监控主机、动环主机"),
            _item("MONITORING_COLLECTOR", "数据采集器", "采集器、动环采集器、IO采集模块"),
            _item("MONITORING_IO_MODULE", "IO 模块", "DI模块、DO模块、AI模块、IO扩展模块"),
            _item("MONITORING_GATEWAY", "监控网关", "动环网关、协议网关、采集网关"),
            _item("MONITORING_DISPLAY", "监控显示终端", "显示器、监控终端"),
            _item("MONITORING_POWER_SUPPLY", "监控电源模块", "电源模块、开关电源"),
        ),
    ),
    VocabularyCategory(
        "ROOM_ENVIRONMENT",
        "ROOM_ENVIRONMENT",
        "机房环境",
        (
            _item("ROOM_TEMP_HUMIDITY_SENSOR", "温湿度传感器", "温湿度探头、环境温湿度传感器"),
            _item("ROOM_WATER_LEAK_SENSOR", "漏水传感器", "漏水检测器、漏水绳、漏水探头"),
            _item("ROOM_SMOKE_SENSOR", "烟雾传感器", "烟感、烟雾探测器"),
            _item("ROOM_DOOR_SENSOR", "门磁传感器", "门磁、门状态传感器"),
            _item("ROOM_AIR_QUALITY_SENSOR", "空气质量传感器", "空气质量探头、环境传感器"),
        ),
    ),
    VocabularyCategory(
        "TRANSMISSION",
        "TRANSMISSION",
        "传输",
        (
            _item("OPTICAL_TRANSCEIVER", "光模块", "光收发模块、SFP、SFP+、QSFP、QSFP28"),
            _item("OPTICAL_FIBER", "光纤跳线", "光纤、光跳线、尾纤"),
            _item("NETWORK_SWITCH", "网络交换机", "交换机、以太网交换机"),
            _item("TRANSMISSION_BOARD", "传输业务板卡", "业务板、传输板卡、接口板"),
            _item("TRANSMISSION_POWER_MODULE", "传输设备电源模块", "电源板、电源模块"),
            _item("ODF_COMPONENT", "ODF 配线组件", "ODF模块、光纤配线模块"),
        ),
    ),
    VocabularyCategory(
        "SERVER",
        "SERVER",
        "服务器",
        (
            _item("SERVER_CPU", "服务器 CPU", "处理器、CPU、服务器处理器"),
            _item("SERVER_MEMORY", "服务器内存", "内存、内存条、DIMM"),
            _item("SERVER_SSD", "服务器 SSD", "固态硬盘、SSD、企业级SSD"),
            _item("SERVER_HDD", "服务器 HDD", "机械硬盘、HDD、企业级硬盘"),
            _item("SERVER_POWER_SUPPLY", "服务器电源", "PSU、电源模块、服务器PSU"),
            _item("SERVER_FAN", "服务器风扇", "散热风扇、风扇模块"),
            _item("SERVER_RAID_CARD", "RAID 卡", "阵列卡、RAID控制器"),
            _item("SERVER_NIC", "服务器网卡", "NIC、网络适配器、以太网卡"),
            _item("SERVER_GPU", "GPU 加速卡", "GPU、计算卡、AI加速卡"),
        ),
    ),
    VocabularyCategory(
        "MAINTENANCE_TOOL",
        "OM_TOOL",
        "运维工具",
        (
            _item("MULTIMETER", "数字万用表", "万用表、电工万用表"),
            _item("CLAMP_METER", "钳形电流表", "钳形表、钳表"),
            _item("INSULATION_TESTER", "绝缘电阻测试仪", "摇表、兆欧表、绝缘测试仪"),
            _item("THERMAL_CAMERA", "红外热像仪", "热成像仪、红外测温仪"),
            _item("NETWORK_TESTER", "网络测试仪", "网线测试仪、网络检测仪"),
            _item("OPTICAL_POWER_METER", "光功率计", "光功率测试仪"),
            _item("FIBER_FAULT_LOCATOR", "红光笔", "光纤故障定位仪、VFL"),
            _item("PORTABLE_TEMP_HUMIDITY_METER", "便携式温湿度仪", "温湿度计、环境检测仪"),
        ),
    ),
)

ALL_ITEMS = tuple((category, item) for category in VOCABULARY for item in category.items)
