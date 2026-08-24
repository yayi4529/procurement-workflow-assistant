"""Create or remove the isolated development database's TEST demo data."""

import argparse
import asyncio
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.db.session import engine
from app.models.agent import AgentConversation, AgentMessage, AgentSessionState
from app.models.assets import (
    Asset,
    AssetComponent,
    AssetRelation,
    EquipmentCategory,
    EquipmentModel,
)
from app.models.identity import (
    Employee,
    EmployeeBuilding,
    EmployeeExternalIdentity,
    EmployeeRole,
)
from app.models.notification import NotificationOutbox
from app.models.procurement import (
    PurchaseExecution,
    PurchaseOperationLog,
    PurchaseRequest,
    PurchaseRequestItem,
    PurchaseReview,
    PurchaseReviewItem,
    Supplier,
    SupplierBlacklist,
    WarehouseReceipt,
)

EMPLOYEE_IDS = list(range(90001, 90009))
REQUEST_IDS = list(range(91001, 91010))
SUPPLIER_IDS = list(range(92001, 92006))
CONVERSATION_IDS = list(range(93001, 93005))
ASSET_IDS = list(range(95101, 95106))
MODEL_IDS = list(range(95201, 95205))
DEMO_PLATFORM_TYPE = "TEST_PLATFORM"

T0 = datetime(2026, 7, 1, 9, 0, 0)


async def clean_demo_data(connection) -> None:
    await connection.execute(
        delete(AssetRelation).where(
            (AssetRelation.source_asset_id.in_(ASSET_IDS))
            | (AssetRelation.target_asset_id.in_(ASSET_IDS))
        )
    )
    await connection.execute(delete(AssetComponent).where(AssetComponent.asset_id.in_(ASSET_IDS)))
    await connection.execute(delete(Asset).where(Asset.asset_id.in_(ASSET_IDS)))
    await connection.execute(delete(EquipmentModel).where(EquipmentModel.model_id.in_(MODEL_IDS)))
    interactive_request_ids = list(
        (
            await connection.execute(
                select(PurchaseRequest.request_id).where(
                    PurchaseRequest.applicant_employee_id.in_(EMPLOYEE_IDS),
                    PurchaseRequest.request_no.like("PR-%"),
                )
            )
        ).scalars()
    )
    cleanup_request_ids = [*REQUEST_IDS, *interactive_request_ids]
    interactive_conversation_ids = list(
        (
            await connection.execute(
                select(AgentConversation.conversation_id).where(
                    AgentConversation.purchase_request_id.in_(cleanup_request_ids)
                )
            )
        ).scalars()
    )
    cleanup_conversation_ids = [*CONVERSATION_IDS, *interactive_conversation_ids]
    await connection.execute(
        delete(AgentSessionState).where(
            AgentSessionState.conversation_id.in_(cleanup_conversation_ids)
        )
    )
    await connection.execute(
        delete(AgentMessage).where(AgentMessage.conversation_id.in_(cleanup_conversation_ids))
    )
    await connection.execute(
        delete(AgentConversation).where(
            AgentConversation.conversation_id.in_(cleanup_conversation_ids)
        )
    )
    await connection.execute(
        delete(NotificationOutbox).where(NotificationOutbox.request_id.in_(cleanup_request_ids))
    )
    await connection.execute(
        delete(WarehouseReceipt).where(WarehouseReceipt.request_id.in_(cleanup_request_ids))
    )
    await connection.execute(
        delete(PurchaseReviewItem).where(
            PurchaseReviewItem.request_item_id.in_(
                select(PurchaseRequestItem.request_item_id).where(
                    PurchaseRequestItem.request_id.in_(cleanup_request_ids)
                )
            )
        )
    )
    await connection.execute(
        delete(SupplierBlacklist).where(
            SupplierBlacklist.source_request_id.in_(cleanup_request_ids)
        )
    )
    await connection.execute(
        delete(PurchaseReview).where(PurchaseReview.request_id.in_(cleanup_request_ids))
    )
    await connection.execute(
        delete(PurchaseExecution).where(PurchaseExecution.request_id.in_(cleanup_request_ids))
    )
    await connection.execute(
        delete(PurchaseRequestItem).where(PurchaseRequestItem.request_id.in_(cleanup_request_ids))
    )
    await connection.execute(
        delete(PurchaseOperationLog).where(PurchaseOperationLog.request_id.in_(cleanup_request_ids))
    )
    await connection.execute(
        delete(PurchaseRequest).where(PurchaseRequest.request_id.in_(cleanup_request_ids))
    )
    await connection.execute(delete(EmployeeRole).where(EmployeeRole.employee_id.in_(EMPLOYEE_IDS)))
    await connection.execute(
        delete(EmployeeBuilding).where(EmployeeBuilding.employee_id.in_(EMPLOYEE_IDS))
    )
    await connection.execute(
        delete(EmployeeExternalIdentity).where(
            EmployeeExternalIdentity.employee_id.in_(EMPLOYEE_IDS),
            EmployeeExternalIdentity.platform_type == DEMO_PLATFORM_TYPE,
        )
    )


async def upsert_rows(connection, model, rows: list[dict], update_columns: tuple[str, ...]) -> None:
    statement = mysql_insert(model).values(rows)
    await connection.execute(
        statement.on_duplicate_key_update(
            **{column: getattr(statement.inserted, column) for column in update_columns}
        )
    )


def equipment_category_rows() -> list[dict]:
    domains = [
        (95001, "POWER", "供配电系统"),
        (95002, "COOLING", "暖通制冷与水系统"),
        (95003, "MONITORING_ENV", "监控与机房环境"),
        (95004, "ICT", "IT与通信系统"),
        (95005, "OM", "运维保障"),
    ]
    types = [
        (95011, 95001, "MV_SWITCHGEAR_10KV", "10kV开关柜"),
        (95012, 95001, "TRANSFORMER", "变压器"),
        (95013, 95001, "LV_SWITCHGEAR_400V", "400V配电柜"),
        (95014, 95001, "UPS", "UPS"),
        (95015, 95001, "HVDC", "高压直流"),
        (95016, 95001, "BATTERY", "蓄电池"),
        (95017, 95002, "CHILLER", "冷水机组"),
        (95018, 95002, "SHU", "SHU"),
        (95019, 95002, "COOLING_TOWER", "冷却塔"),
        (95020, 95002, "COOLING_PUMP", "冷却泵"),
        (95021, 95002, "WATER_SYSTEM", "水系统"),
        (95022, 95002, "IN_ROW_AC", "列间空调"),
        (95023, 95003, "MONITORING", "监控"),
        (95024, 95003, "ROOM_ENVIRONMENT", "机房环境"),
        (95025, 95004, "TRANSMISSION", "传输"),
        (95026, 95004, "SERVER", "服务器"),
        (95027, 95005, "OM_TOOL", "运维工具"),
    ]
    return [
        {
            "category_id": category_id,
            "parent_category_id": None,
            "category_code": code,
            "category_name": name,
            "category_level": 1,
            "description": "TEST 基础分类",
            "sort_order": order,
            "status": "ACTIVE",
        }
        for order, (category_id, code, name) in enumerate(domains, start=1)
    ] + [
        {
            "category_id": category_id,
            "parent_category_id": parent_id,
            "category_code": code,
            "category_name": name,
            "category_level": 2,
            "description": "TEST 设备分类",
            "sort_order": order,
            "status": "ACTIVE",
        }
        for order, (category_id, parent_id, code, name) in enumerate(types, start=1)
    ]


def equipment_model_rows() -> list[dict]:
    return [
        {
            "model_id": 95201,
            "category_id": 95014,
            "brand": "TEST-BRAND",
            "model": "TEST-UPS-500",
            "model_name": "TEST UPS 型号",
            "specifications": {"capacity_kva": 500, "modular": True},
            "default_unit": "台",
            "lifecycle_status": "ACTIVE",
            "remark": "TEST DATA",
        },
        {
            "model_id": 95202,
            "category_id": 95016,
            "brand": "TEST-BRAND",
            "model": "TEST-BAT-100",
            "model_name": "TEST 蓄电池型号",
            "specifications": {"nominal_voltage_v": 12, "capacity_ah": 100},
            "default_unit": "组",
            "lifecycle_status": "ACTIVE",
            "remark": "TEST DATA",
        },
        {
            "model_id": 95203,
            "category_id": 95017,
            "brand": "TEST-BRAND",
            "model": "TEST-CH-1200",
            "model_name": "TEST 冷水机组型号",
            "specifications": {"cooling_capacity_kw": 1200},
            "default_unit": "台",
            "lifecycle_status": "ACTIVE",
            "remark": "TEST DATA",
        },
        {
            "model_id": 95204,
            "category_id": 95026,
            "brand": "TEST-BRAND",
            "model": "TEST-SRV-2U",
            "model_name": "TEST 服务器型号",
            "specifications": {"form_factor": "2U", "memory_gb": 512},
            "default_unit": "台",
            "lifecycle_status": "ACTIVE",
            "remark": "TEST DATA",
        },
    ]


def asset_rows() -> list[dict]:
    base = {
        "status": "ACTIVE",
        "criticality": "HIGH",
        "commissioned_at": date(2025, 1, 1),
        "warranty_end_at": date(2028, 1, 1),
        "version": 0,
        "remark": "TEST DATA",
    }
    return [
        {
            **base,
            "asset_id": 95101,
            "asset_code": "TEST-UPS-A2-01",
            "asset_name": "一号楼二层2号UPS",
            "category_id": 95014,
            "model_id": 95201,
            "building_id": 1,
            "location": "二层UPS室",
            "serial_number": "TEST-SN-UPS-01",
            "configuration": {"installed_module_count": 8},
            "aliases": ["2号UPS", "二楼2号UPS", "UPS02"],
            "redundancy_group": "TEST-UPS-GROUP-A",
            "redundancy_mode": "TWO_N",
        },
        {
            **base,
            "asset_id": 95102,
            "asset_code": "TEST-BAT-A2-01",
            "asset_name": "一号楼二层2号蓄电池组",
            "category_id": 95016,
            "model_id": 95202,
            "building_id": 1,
            "location": "二层电池室",
            "serial_number": "TEST-SN-BAT-01",
            "configuration": {},
            "aliases": ["2号电池组"],
            "redundancy_group": None,
            "redundancy_mode": None,
        },
        {
            **base,
            "asset_id": 95103,
            "asset_code": "TEST-CH-01",
            "asset_name": "一号楼1号冷水机组",
            "category_id": 95017,
            "model_id": 95203,
            "building_id": 1,
            "location": "制冷站",
            "serial_number": "TEST-SN-CH-01",
            "configuration": {},
            "aliases": ["1号冷机"],
            "redundancy_group": None,
            "redundancy_mode": None,
        },
        {
            **base,
            "asset_id": 95104,
            "asset_code": "TEST-SRV-A-001",
            "asset_name": "一号楼测试服务器001",
            "category_id": 95026,
            "model_id": 95204,
            "building_id": 1,
            "location": "二层A机房",
            "serial_number": "TEST-SN-SRV-001",
            "configuration": {"installed_memory_gb": 512},
            "aliases": ["测试服务器001"],
            "redundancy_group": None,
            "redundancy_mode": None,
        },
        {
            **base,
            "asset_id": 95105,
            "asset_code": "TEST-UPS-B2-01",
            "asset_name": "二号楼二层2号UPS",
            "category_id": 95014,
            "model_id": None,
            "building_id": 2,
            "location": "二层UPS室",
            "serial_number": "TEST-SN-UPS-02",
            "configuration": {},
            "aliases": ["2号UPS", "二楼2号UPS", "UPS02"],
            "redundancy_group": None,
            "redundancy_mode": None,
        },
    ]


def component_rows() -> list[dict]:
    names = [
        (95301, 95101, "功率模块", "POWER_MODULE", 8, "块"),
        (95302, 95101, "控制模块", "CONTROL_MODULE", 1, "套"),
        (95303, 95101, "旁路模块", "BYPASS_MODULE", 1, "套"),
        (95304, 95104, "CPU", "CPU", 2, "个"),
        (95305, 95104, "内存", "MEMORY", 16, "条"),
        (95306, 95104, "硬盘", "DISK", 8, "块"),
        (95307, 95104, "电源", "POWER_SUPPLY", 2, "个"),
    ]
    return [
        {
            "component_id": component_id,
            "asset_id": asset_id,
            "component_name": name,
            "component_category": category,
            "brand": None,
            "model_or_part_no": None,
            "quantity": Decimal(quantity),
            "unit": unit,
            "status": "NORMAL",
            "replaceable": True,
            "remark": "TEST DATA",
        }
        for component_id, asset_id, name, category, quantity, unit in names
    ]


def relation_rows() -> list[dict]:
    return [
        {
            "relation_id": 95401,
            "source_asset_id": 95101,
            "relation_type": "CONNECTED_TO",
            "target_asset_id": 95102,
            "remark": "TEST UPS 与电池组",
            "status": "ACTIVE",
        },
        {
            "relation_id": 95402,
            "source_asset_id": 95104,
            "relation_type": "POWERED_BY",
            "target_asset_id": 95101,
            "remark": "TEST 服务器供电",
            "status": "ACTIVE",
        },
        {
            "relation_id": 95403,
            "source_asset_id": 95104,
            "relation_type": "COOLED_BY",
            "target_asset_id": 95103,
            "remark": "TEST 服务器制冷",
            "status": "ACTIVE",
        },
    ]


def employee_rows() -> list[dict]:
    names = [
        ("TEST-E001", "测试需求人", "13800009001", True),
        ("TEST-E002", "测试一号楼楼长", "13800009002", True),
        ("TEST-E003", "测试采购员", "13800009003", True),
        ("TEST-E004", "测试仓库管理员", "13800009004", True),
        ("TEST-E005", "测试系统管理员", "13800009005", True),
        ("TEST-E006", "测试停用员工", "13800009006", False),
        ("TEST-E007", "测试二号楼楼长", "13800009007", True),
        ("TEST-E008", "测试多角色员工", "13800009008", True),
    ]
    return [
        {
            "employee_id": employee_id,
            "employee_no": employee_no,
            "name": name,
            "mobile": mobile,
            "status": status,
        }
        for employee_id, (employee_no, name, mobile, status) in zip(
            EMPLOYEE_IDS, names, strict=True
        )
    ]


def identity_rows() -> list[dict]:
    return [
        {
            "identity_id": 94000 + index,
            "employee_id": employee_id,
            "platform_type": DEMO_PLATFORM_TYPE,
            "platform_user_id": f"test-user-{index:02d}",
            "status": employee_id != 90006,
            "last_synced_at": T0,
        }
        for index, employee_id in enumerate(EMPLOYEE_IDS, start=1)
    ]


def employee_role_rows() -> list[dict]:
    assignments = [
        (90001, 1),
        (90002, 2),
        (90003, 3),
        (90004, 4),
        (90005, 5),
        (90006, 1),
        (90007, 2),
        (90008, 1),
        (90008, 3),
    ]
    return [
        {
            "employee_id": employee_id,
            "role_id": role_id,
            "status": employee_id != 90006,
            "synced_at": T0,
        }
        for employee_id, role_id in assignments
    ]


def employee_building_rows() -> list[dict]:
    assignments = [
        (90001, 1, True),
        (90002, 1, True),
        (90006, 1, True),
        (90007, 2, True),
        (90008, 1, True),
        (90008, 2, False),
    ]
    return [
        {
            "employee_id": employee_id,
            "building_id": building_id,
            "is_primary": is_primary,
            "status": employee_id != 90006,
            "synced_at": T0,
        }
        for employee_id, building_id, is_primary in assignments
    ]


def supplier_rows() -> list[dict]:
    return [
        {
            "supplier_id": 92001,
            "supplier_name": "TEST-常规供应商A",
            "unified_social_credit_code": "TEST-CREDIT-92001",
            "bank_name": "测试银行",
            "bank_account": "TEST-ACCOUNT-92001",
            "registered_address": "测试市采购路1号",
            "contract_contact_info": "测试联系人A 13900009201",
            "status": True,
        },
        {
            "supplier_id": 92002,
            "supplier_name": "TEST-供应商B（主档已更新）",
            "unified_social_credit_code": "TEST-CREDIT-92002",
            "bank_name": "测试银行",
            "bank_account": "TEST-ACCOUNT-92002-NEW",
            "registered_address": "测试市采购路2号新址",
            "contract_contact_info": "测试联系人B 13900009202",
            "status": True,
        },
        {
            "supplier_id": 92003,
            "supplier_name": "TEST-永久黑名单供应商",
            "unified_social_credit_code": "TEST-CREDIT-92003",
            "bank_name": None,
            "bank_account": None,
            "registered_address": None,
            "contract_contact_info": None,
            "status": True,
        },
        {
            "supplier_id": 92004,
            "supplier_name": "TEST-限时黑名单供应商",
            "unified_social_credit_code": "TEST-CREDIT-92004",
            "bank_name": None,
            "bank_account": None,
            "registered_address": None,
            "contract_contact_info": None,
            "status": True,
        },
        {
            "supplier_id": 92005,
            "supplier_name": "TEST-已解除黑名单供应商",
            "unified_social_credit_code": "TEST-CREDIT-92005",
            "bank_name": None,
            "bank_account": None,
            "registered_address": None,
            "contract_contact_info": None,
            "status": True,
        },
    ]


def request_rows() -> list[dict]:
    scenarios = [
        (91001, "TEST-PR-DRAFT", "DRAFT", "测试草稿设备", 1, 90001, None, None),
        (
            91002,
            "TEST-PR-PENDING-REVIEW",
            "PENDING_REVIEW",
            "测试待审核设备",
            2,
            90002,
            T0,
            None,
        ),
        (
            91003,
            "TEST-PR-REJECTED",
            "REJECTED",
            "测试被驳回设备",
            3,
            90001,
            T0,
            None,
        ),
        (
            91004,
            "TEST-PR-PENDING-PURCHASE",
            "PENDING_PURCHASE",
            "测试重提后待采购设备",
            4,
            90003,
            T0,
            None,
        ),
        (
            91005,
            "TEST-PR-PURCHASING",
            "PURCHASING",
            "测试采购中设备",
            5,
            90003,
            T0,
            None,
        ),
        (
            91006,
            "TEST-PR-PENDING-WAREHOUSE",
            "PENDING_WAREHOUSE",
            "测试待入库设备",
            6,
            90004,
            T0,
            None,
        ),
        (
            91007,
            "TEST-PR-COMPLETED-EQUAL",
            "COMPLETED",
            "测试等量入库设备",
            7,
            None,
            T0,
            datetime(2026, 7, 8, 16, 0, 0),
        ),
        (
            91008,
            "TEST-PR-COMPLETED-LESS",
            "COMPLETED",
            "测试少量入库设备",
            8,
            None,
            T0,
            datetime(2026, 7, 9, 16, 0, 0),
        ),
        (
            91009,
            "TEST-PR-COMPLETED-EXACT-2",
            "COMPLETED",
            "测试第二组等量入库设备",
            9,
            None,
            T0,
            datetime(2026, 7, 10, 16, 0, 0),
        ),
    ]
    return [
        {
            "request_id": request_id,
            "request_no": request_no,
            "building_id": 1,
            "applicant_employee_id": 90001,
            "applicant_platform_type_snapshot": "TEST_PLATFORM",
            "applicant_platform_user_id_snapshot": "test-user-01",
            "applicant_name_snapshot": "测试需求人",
            "applicant_mobile_snapshot": "13800009001",
            "device_profession": "算力服务器",
            "device_name": device_name,
            "brand": "TEST-BRAND",
            "model": f"TEST-MODEL-{request_id}",
            "quantity": Decimal(quantity),
            "unit": "台",
            "application_reason": f"TEST 场景：{status}",
            "applicant_remark": "仅用于开发测试",
            "status": status,
            "current_handler_employee_id": handler_id,
            "version": max(request_id - 91001, 0),
            "submitted_at": submitted_at,
            "completed_at": completed_at,
        }
        for (
            request_id,
            request_no,
            status,
            device_name,
            quantity,
            handler_id,
            submitted_at,
            completed_at,
        ) in scenarios
    ]


def review_rows() -> list[dict]:
    rows = [
        (95002, 91002, 1, "DRAFT", None, None, False),
        (95003, 91003, 1, "COMPLETED", "REJECTED", "预算说明不足", False),
        (95004, 91004, 1, "COMPLETED", "REJECTED", "首次审核驳回", False),
        (95005, 91004, 2, "COMPLETED", "APPROVED", "补充说明后通过", True),
        (95006, 91005, 1, "COMPLETED", "APPROVED", "审核通过", False),
        (95007, 91006, 1, "COMPLETED", "APPROVED", "审核通过", True),
        (95008, 91007, 1, "COMPLETED", "APPROVED", "审核通过", True),
        (95009, 91008, 1, "COMPLETED", "APPROVED", "审核通过", False),
        (95010, 91009, 1, "COMPLETED", "APPROVED", "审核通过", False),
    ]
    result = []
    for review_id, request_id, round_no, status, decision, opinion, need_contract in rows:
        completed = status == "COMPLETED"
        result.append(
            {
                "review_id": review_id,
                "request_id": request_id,
                "review_round": round_no,
                "review_status": status,
                "reviewer_employee_id": 90002,
                "reviewer_platform_type_snapshot": "TEST_PLATFORM",
                "reviewer_platform_user_id_snapshot": "test-user-02",
                "reviewer_name_snapshot": "测试一号楼楼长",
                "reviewer_mobile_snapshot": "13800009002",
                "review_result": decision,
                "review_opinion": opinion,
                "proposed_supplier_id": 92001 if completed and decision == "APPROVED" else None,
                "proposed_supplier_name": (
                    "TEST-常规供应商A" if completed and decision == "APPROVED" else None
                ),
                "supplier_contact_name": "测试联系人A" if completed else None,
                "supplier_contact_info": "13900009201" if completed else None,
                "supplier_link": "https://example.invalid/test-supplier" if completed else None,
                "estimated_unit_price": Decimal("1000.00") if completed else None,
                "estimated_total_price": (
                    Decimal("1000.00") * (request_id - 91000) if completed else None
                ),
                "need_contract": need_contract,
                "contract_type": "设备采购合同" if need_contract else None,
                "payment_method": "验收后付款" if completed else None,
                "expected_arrival_date": date(2026, 8, 1) if completed else None,
                "warranty_info": "三年质保" if completed else None,
                "review_remark": "TEST 审核记录",
                "reviewed_at": datetime(2026, 7, 3, 10, 0, 0) if completed else None,
            }
        )
    return result


def request_item_rows() -> list[dict]:
    return [
        {
            "request_item_id": 98000 + (row["request_id"] - 91000),
            "request_id": row["request_id"],
            "item_no": 1,
            "item_kind": "EQUIPMENT",
            "item_name": row["device_name"],
            "brand_snapshot": row["brand"],
            "model_snapshot": row["model"],
            "quantity": row["quantity"],
            "unit": row["unit"],
            "requires_warehouse": True,
            "item_reason": row["application_reason"],
            "is_active": True,
            "remark": row["applicant_remark"],
        }
        for row in request_rows()
        if row["device_name"] and row["quantity"] and row["unit"]
    ]


def review_item_rows() -> list[dict]:
    requests = {row["request_id"]: row for row in request_item_rows()}
    return [
        {
            "review_item_id": 99000 + (row["review_id"] - 95000),
            "review_id": row["review_id"],
            "request_item_id": requests[row["request_id"]]["request_item_id"],
            "item_kind_snapshot": requests[row["request_id"]]["item_kind"],
            "item_name_snapshot": requests[row["request_id"]]["item_name"],
            "quantity_snapshot": requests[row["request_id"]]["quantity"],
            "unit_snapshot": requests[row["request_id"]]["unit"],
            "brand_snapshot": requests[row["request_id"]]["brand_snapshot"],
            "model_snapshot": requests[row["request_id"]]["model_snapshot"],
            "proposed_supplier_id": row["proposed_supplier_id"],
            "proposed_supplier_name_snapshot": row["proposed_supplier_name"],
            "supplier_contact_name": row["supplier_contact_name"],
            "supplier_contact_info": row["supplier_contact_info"],
            "supplier_link": row["supplier_link"],
            "estimated_unit_price": row["estimated_unit_price"],
            "estimated_total_price": row["estimated_total_price"],
            "need_contract": row["need_contract"],
            "contract_type": row["contract_type"],
            "payment_method": row["payment_method"],
            "expected_arrival_date": row["expected_arrival_date"],
            "warranty_info": row["warranty_info"],
            "item_remark": row["review_remark"],
        }
        for row in review_rows()
    ]


def execution_rows() -> list[dict]:
    rows = [
        (96006, 91006, 92001, "TEST-常规供应商A", "TEST-ACCOUNT-92001", 6),
        (
            96007,
            91007,
            92002,
            "TEST-供应商B（本次采购快照旧名称）",
            "TEST-ACCOUNT-92002-OLD",
            7,
        ),
        (96008, 91008, 92001, "TEST-常规供应商A", "TEST-ACCOUNT-92001", 8),
        (96009, 91009, 92001, "TEST-常规供应商A", "TEST-ACCOUNT-92001", 9),
    ]
    return [
        {
            "execution_id": execution_id,
            "request_id": request_id,
            "request_item_id": 98000 + (request_id - 91000),
            "purchaser_employee_id": 90003,
            "purchaser_platform_type_snapshot": "TEST_PLATFORM",
            "purchaser_platform_user_id_snapshot": "test-user-03",
            "purchaser_name_snapshot": "测试采购员",
            "purchaser_mobile_snapshot": "13800009003",
            "supplier_id": supplier_id,
            "supplier_name_snapshot": supplier_name,
            "supplier_tax_no_snapshot": f"TEST-CREDIT-{supplier_id}",
            "supplier_bank_name_snapshot": "测试银行",
            "supplier_bank_account_snapshot": bank_account,
            "supplier_address_snapshot": "TEST-采购时地址快照",
            "contract_contact_info_snapshot": "TEST-采购时联系人快照",
            "actual_unit_price": Decimal("950.00"),
            "purchased_quantity": Decimal(quantity),
            "actual_total_price": Decimal("950.00") * quantity,
            "tax_rate": Decimal("13.00"),
            "purchased_at": datetime(2026, 7, 6, 14, 0, 0),
            "execution_remark": "TEST 采购执行",
        }
        for execution_id, request_id, supplier_id, supplier_name, bank_account, quantity in rows
    ]


def receipt_rows() -> list[dict]:
    return [
        {
            "receipt_id": 97007,
            "request_id": 91007,
            "execution_id": 96007,
            "warehouse_employee_id": 90004,
            "warehouse_platform_type_snapshot": "TEST_PLATFORM",
            "warehouse_platform_user_id_snapshot": "test-user-04",
            "warehouse_name_snapshot": "测试仓库管理员",
            "warehouse_mobile_snapshot": "13800009004",
            "warehouse_location": "TEST-A区-01",
            "received_quantity": Decimal("7.000"),
            "receipt_remark": "申请 7 台，等量入库",
            "received_at": datetime(2026, 7, 8, 16, 0, 0),
        },
        {
            "receipt_id": 97008,
            "request_id": 91008,
            "execution_id": 96008,
            "warehouse_employee_id": 90004,
            "warehouse_platform_type_snapshot": "TEST_PLATFORM",
            "warehouse_platform_user_id_snapshot": "test-user-04",
            "warehouse_name_snapshot": "测试仓库管理员",
            "warehouse_mobile_snapshot": "13800009004",
            "warehouse_location": "TEST-A区-02",
            "received_quantity": Decimal("6.000"),
            "receipt_remark": "申请 8 台，2 台延期到货；少量入库说明必填场景",
            "received_at": datetime(2026, 7, 9, 16, 0, 0),
        },
        {
            "receipt_id": 97009,
            "request_id": 91009,
            "execution_id": 96009,
            "warehouse_employee_id": 90004,
            "warehouse_platform_type_snapshot": "TEST_PLATFORM",
            "warehouse_platform_user_id_snapshot": "test-user-04",
            "warehouse_name_snapshot": "测试仓库管理员",
            "warehouse_mobile_snapshot": "13800009004",
            "warehouse_location": "TEST-A区-03",
            "received_quantity": Decimal("9.000"),
            "receipt_remark": "申请 9 台，等量入库",
            "received_at": datetime(2026, 7, 10, 16, 0, 0),
        },
    ]


def blacklist_rows() -> list[dict]:
    common = {
        "registrar_employee_id": 90002,
        "registrar_platform_type_snapshot": "TEST_PLATFORM",
        "registrar_platform_user_id_snapshot": "test-user-02",
        "registrar_name_snapshot": "测试一号楼楼长",
        "registrar_mobile_snapshot": "13800009002",
        "blacklist_type": "履约问题",
        "blacklist_reason": "TEST 黑名单场景",
        "start_at": datetime(2026, 7, 4, 10, 0, 0),
    }
    return [
        {
            **common,
            "blacklist_id": 98001,
            "supplier_id": 92003,
            "supplier_name_snapshot": "TEST-永久黑名单供应商",
            "source_request_id": 91003,
            "duration_type": "PERMANENT",
            "end_at": None,
            "released_at": None,
            "released_by_employee_id": None,
            "release_reason": None,
            "status": "ACTIVE",
        },
        {
            **common,
            "blacklist_id": 98002,
            "supplier_id": 92004,
            "supplier_name_snapshot": "TEST-限时黑名单供应商",
            "source_request_id": 91003,
            "duration_type": "LIMITED",
            "end_at": datetime(2026, 12, 31, 23, 59, 59),
            "released_at": None,
            "released_by_employee_id": None,
            "release_reason": None,
            "status": "ACTIVE",
        },
        {
            **common,
            "blacklist_id": 98003,
            "supplier_id": 92005,
            "supplier_name_snapshot": "TEST-已解除黑名单供应商",
            "source_request_id": 91004,
            "duration_type": "LIMITED",
            "end_at": datetime(2026, 12, 31, 23, 59, 59),
            "released_at": datetime(2026, 7, 20, 10, 0, 0),
            "released_by_employee_id": 90005,
            "release_reason": "TEST 管理员提前解除",
            "status": "RELEASED",
        },
    ]


def operation_log_rows() -> list[dict]:
    actions = [
        (99001, 91001, 90001, 1, "需求人", "CREATE_DRAFT", None, "DRAFT", 90001),
        (99002, 91002, 90001, 1, "需求人", "SUBMIT", "DRAFT", "PENDING_REVIEW", 90002),
        (99003, 91003, 90002, 2, "楼长", "REJECT", "PENDING_REVIEW", "REJECTED", 90001),
        (99004, 91004, 90001, 1, "需求人", "RESUBMIT", "REJECTED", "PENDING_REVIEW", 90002),
        (
            99005,
            91004,
            90002,
            2,
            "楼长",
            "APPROVE",
            "PENDING_REVIEW",
            "PENDING_PURCHASE",
            90003,
        ),
        (
            99006,
            91006,
            90003,
            3,
            "采购员",
            "COMPLETE_PURCHASE",
            "PURCHASING",
            "PENDING_WAREHOUSE",
            90004,
        ),
        (
            99007,
            91007,
            90004,
            4,
            "仓库管理员",
            "WAREHOUSE_RECEIVE",
            "PENDING_WAREHOUSE",
            "COMPLETED",
            None,
        ),
        (
            99008,
            91008,
            90004,
            4,
            "仓库管理员",
            "WAREHOUSE_RECEIVE_LESS",
            "PENDING_WAREHOUSE",
            "COMPLETED",
            None,
        ),
        (
            99009,
            91009,
            90004,
            4,
            "仓库管理员",
            "WAREHOUSE_RECEIVE_MORE",
            "PENDING_WAREHOUSE",
            "COMPLETED",
            None,
        ),
    ]
    user_numbers = {90001: "01", 90002: "02", 90003: "03", 90004: "04"}
    names = {
        90001: "测试需求人",
        90002: "测试一号楼楼长",
        90003: "测试采购员",
        90004: "测试仓库管理员",
    }
    return [
        {
            "log_id": log_id,
            "request_id": request_id,
            "operator_employee_id": employee_id,
            "operator_platform_type_snapshot": "TEST_PLATFORM",
            "operator_platform_user_id_snapshot": f"test-user-{user_numbers[employee_id]}",
            "operator_name_snapshot": names[employee_id],
            "operator_mobile_snapshot": f"138000090{user_numbers[employee_id]}",
            "operator_role_id_snapshot": role_id,
            "operator_role_name_snapshot": role_name,
            "assigned_to_employee_id": assigned_to,
            "action_token": f"TEST-ACTION-{log_id}",
            "action_type": action_type,
            "from_status": from_status,
            "to_status": to_status,
            "operation_summary": f"TEST {action_type}",
            "operated_at": datetime(2026, 7, 2, 10, 0, 0),
        }
        for (
            log_id,
            request_id,
            employee_id,
            role_id,
            role_name,
            action_type,
            from_status,
            to_status,
            assigned_to,
        ) in actions
    ]


def conversation_rows() -> list[dict]:
    statuses = ["ACTIVE", "COMPLETED", "CANCELLED", "EXPIRED"]
    return [
        {
            "conversation_id": conversation_id,
            "employee_id": 90001,
            "platform_type": "TEST_PLATFORM",
            "external_conversation_id": f"TEST-CONVERSATION-{index}",
            "purchase_request_id": 91000 + index,
            "status": status,
            "started_at": T0,
            "last_active_at": datetime(2026, 7, 1, 9, index, 0),
        }
        for index, (conversation_id, status) in enumerate(
            zip(CONVERSATION_IDS, statuses, strict=True), start=1
        )
    ]


async def seed_demo_data() -> None:
    async with engine.begin() as connection:
        await clean_demo_data(connection)
        await upsert_rows(
            connection,
            EquipmentCategory,
            equipment_category_rows(),
            (
                "parent_category_id",
                "category_name",
                "category_level",
                "description",
                "sort_order",
                "status",
            ),
        )
        await connection.execute(insert(EquipmentModel), equipment_model_rows())
        await upsert_rows(
            connection,
            Employee,
            employee_rows(),
            ("employee_no", "name", "mobile", "status"),
        )
        await connection.execute(insert(EmployeeExternalIdentity), identity_rows())
        await connection.execute(insert(EmployeeRole), employee_role_rows())
        await connection.execute(insert(EmployeeBuilding), employee_building_rows())
        await connection.execute(insert(Asset), asset_rows())
        await connection.execute(insert(AssetComponent), component_rows())
        await connection.execute(insert(AssetRelation), relation_rows())
        await upsert_rows(
            connection,
            Supplier,
            supplier_rows(),
            (
                "supplier_name",
                "unified_social_credit_code",
                "bank_name",
                "bank_account",
                "registered_address",
                "contract_contact_info",
                "status",
            ),
        )
        await connection.execute(insert(PurchaseRequest), request_rows())
        await connection.execute(insert(PurchaseRequestItem), request_item_rows())
        await connection.execute(insert(PurchaseReview), review_rows())
        await connection.execute(insert(PurchaseReviewItem), review_item_rows())
        await connection.execute(insert(PurchaseExecution), execution_rows())
        await connection.execute(insert(WarehouseReceipt), receipt_rows())
        await connection.execute(insert(SupplierBlacklist), blacklist_rows())
        await connection.execute(insert(PurchaseOperationLog), operation_log_rows())
        await connection.execute(insert(AgentConversation), conversation_rows())
        await connection.execute(
            insert(AgentMessage),
            [
                {
                    "message_id": 99501,
                    "conversation_id": 93001,
                    "external_message_id": "TEST-MESSAGE-USER",
                    "sender_type": "USER",
                    "content": "我要采购测试设备",
                },
                {
                    "message_id": 99502,
                    "conversation_id": 93001,
                    "external_message_id": "TEST-MESSAGE-AGENT",
                    "sender_type": "AGENT",
                    "content": "请确认采购数量",
                },
                {
                    "message_id": 99503,
                    "conversation_id": 93001,
                    "external_message_id": "TEST-MESSAGE-SYSTEM",
                    "sender_type": "SYSTEM",
                    "content": "TEST 会话状态已保存",
                },
            ],
        )
        await connection.execute(
            insert(AgentSessionState),
            [
                {
                    "state_id": 99601,
                    "conversation_id": 93001,
                    "current_action": "CREATE_REQUEST",
                    "state_data": {"device_name": "测试草稿设备", "quantity": 1},
                    "missing_fields": ["application_reason"],
                    "confirmed": False,
                    "saved_at": datetime(2026, 7, 1, 9, 5, 0),
                }
            ],
        )
        await connection.execute(
            insert(NotificationOutbox),
            [
                {
                    "notification_id": 99701,
                    "request_id": 91004,
                    "event_type": "REVIEW_APPROVED",
                    "receiver_employee_id": 90003,
                    "platform_type": "TEST_PLATFORM",
                    "receiver_platform_user_id_snapshot": "test-user-03",
                    "dedup_key": "TEST-NOTIFICATION-PENDING",
                    "payload": {"request_no": "TEST-PR-PENDING-PURCHASE"},
                    "status": "PENDING",
                    "retry_count": 0,
                    "next_retry_at": None,
                    "last_error": None,
                    "sent_at": None,
                },
                {
                    "notification_id": 99702,
                    "request_id": 91007,
                    "event_type": "PURCHASE_COMPLETED",
                    "receiver_employee_id": 90001,
                    "platform_type": "TEST_PLATFORM",
                    "receiver_platform_user_id_snapshot": "test-user-01",
                    "dedup_key": "TEST-NOTIFICATION-SENT",
                    "payload": {"request_no": "TEST-PR-COMPLETED-EQUAL"},
                    "status": "SENT",
                    "retry_count": 0,
                    "next_retry_at": None,
                    "last_error": None,
                    "sent_at": datetime(2026, 7, 8, 16, 5, 0),
                },
                {
                    "notification_id": 99703,
                    "request_id": 91006,
                    "event_type": "WAREHOUSE_PENDING",
                    "receiver_employee_id": 90004,
                    "platform_type": "TEST_PLATFORM",
                    "receiver_platform_user_id_snapshot": "test-user-04",
                    "dedup_key": "TEST-NOTIFICATION-FAILED",
                    "payload": {"request_no": "TEST-PR-PENDING-WAREHOUSE"},
                    "status": "FAILED",
                    "retry_count": 3,
                    "next_retry_at": datetime(2026, 7, 7, 10, 0, 0),
                    "last_error": "TEST 模拟通知发送失败",
                    "sent_at": None,
                },
            ],
        )


async def validate_demo_data() -> None:
    async with engine.connect() as connection:
        statuses = set(
            (
                await connection.execute(
                    select(PurchaseRequest.status).where(
                        PurchaseRequest.request_id.in_(REQUEST_IDS)
                    )
                )
            ).scalars()
        )
        receipt_result = await connection.execute(
            select(WarehouseReceipt.request_id, WarehouseReceipt.received_quantity).where(
                WarehouseReceipt.request_id.in_([91007, 91008, 91009])
            )
        )
        receipt_quantities = {row.request_id: row.received_quantity for row in receipt_result.all()}
        notification_statuses = set(
            (
                await connection.execute(
                    select(NotificationOutbox.status).where(
                        NotificationOutbox.request_id.in_(REQUEST_IDS)
                    )
                )
            ).scalars()
        )
        conversation_statuses = set(
            (
                await connection.execute(
                    select(AgentConversation.status).where(
                        AgentConversation.conversation_id.in_(CONVERSATION_IDS)
                    )
                )
            ).scalars()
        )
        count_queries = {
            "employees": (Employee, Employee.employee_id, EMPLOYEE_IDS),
            "suppliers": (Supplier, Supplier.supplier_id, SUPPLIER_IDS),
            "requests": (PurchaseRequest, PurchaseRequest.request_id, REQUEST_IDS),
            "reviews": (PurchaseReview, PurchaseReview.request_id, REQUEST_IDS),
            "executions": (PurchaseExecution, PurchaseExecution.request_id, REQUEST_IDS),
            "receipts": (WarehouseReceipt, WarehouseReceipt.request_id, REQUEST_IDS),
            "blacklists": (
                SupplierBlacklist,
                SupplierBlacklist.source_request_id,
                REQUEST_IDS,
            ),
            "logs": (PurchaseOperationLog, PurchaseOperationLog.request_id, REQUEST_IDS),
            "conversations": (
                AgentConversation,
                AgentConversation.conversation_id,
                CONVERSATION_IDS,
            ),
            "messages": (AgentMessage, AgentMessage.conversation_id, CONVERSATION_IDS),
            "session_states": (
                AgentSessionState,
                AgentSessionState.conversation_id,
                CONVERSATION_IDS,
            ),
            "notifications": (
                NotificationOutbox,
                NotificationOutbox.request_id,
                REQUEST_IDS,
            ),
        }
        table_counts = {}
        for name, (model, id_column, ids) in count_queries.items():
            table_counts[name] = await connection.scalar(
                select(func.count()).select_from(model).where(id_column.in_(ids))
            )

        inactive_employee_count = await connection.scalar(
            select(func.count())
            .select_from(Employee)
            .where(Employee.employee_id.in_(EMPLOYEE_IDS), Employee.status.is_(False))
        )
        snapshot_name = await connection.scalar(
            select(PurchaseExecution.supplier_name_snapshot).where(
                PurchaseExecution.request_id == 91007
            )
        )
        supplier_master_name = await connection.scalar(
            select(Supplier.supplier_name).where(Supplier.supplier_id == 92002)
        )

    expected_statuses = {
        "DRAFT",
        "PENDING_REVIEW",
        "REJECTED",
        "PENDING_PURCHASE",
        "PURCHASING",
        "PENDING_WAREHOUSE",
        "COMPLETED",
    }
    assert statuses == expected_statuses
    assert receipt_quantities == {
        91007: Decimal("7.000"),
        91008: Decimal("6.000"),
        91009: Decimal("9.000"),
    }
    assert notification_statuses == {"PENDING", "SENT", "FAILED"}
    assert conversation_statuses == {"ACTIVE", "COMPLETED", "CANCELLED", "EXPIRED"}
    assert table_counts == {
        "employees": 8,
        "suppliers": 5,
        "requests": 9,
        "reviews": 9,
        "executions": 4,
        "receipts": 3,
        "blacklists": 3,
        "logs": 9,
        "conversations": 4,
        "messages": 3,
        "session_states": 1,
        "notifications": 3,
    }
    assert inactive_employee_count == 1
    assert snapshot_name == "TEST-供应商B（本次采购快照旧名称）"
    assert supplier_master_name == "TEST-供应商B（主档已更新）"


async def main(clean_only: bool) -> None:
    if clean_only:
        async with engine.begin() as connection:
            await clean_demo_data(connection)
        print("TEST demo data removed.")
        return

    await seed_demo_data()
    await validate_demo_data()
    print("TEST demo data created and validated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove only the TEST demo records created by this script.",
    )
    arguments = parser.parse_args()
    asyncio.run(main(arguments.clean))
