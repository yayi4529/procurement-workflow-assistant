"""Generate, seed, validate, and safely clean Task08 synthetic purchase history."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select
from task08_vocabulary import ALL_ITEMS, VOCABULARY, VocabularyCategory, VocabularyItem

from app.core.config import get_settings
from app.db.session import async_session_factory, engine
from app.models.assets import EquipmentCategory, EquipmentModel
from app.models.identity import Building, Employee
from app.models.procurement import (
    PurchaseExecution,
    PurchaseRequest,
    PurchaseRequestItem,
    Supplier,
    SupplierBlacklist,
    WarehouseReceipt,
)

TOTAL_PURCHASE_ITEMS = 2000
RANDOM_SEED = 20260819
SUPPLIER_COUNT = 60
BATCH_MARKER = "TASK08_SYNTHETIC_20260819"
REQUEST_PREFIX = "TEST-T08SYN-"
CREDIT_PREFIX = "T08SYN-CREDIT-"
MANIFEST_PATH = Path(__file__).resolve().parents[1] / ".local" / "task08_seed_manifest.json"

DEVICE_PROFESSION_BY_CATEGORY = {
    "HV_SWITCHGEAR_10KV": "电气",
    "TRANSFORMER": "电气",
    "LV_SWITCHGEAR_400V": "电气",
    "UPS": "电气",
    "HVDC": "电气",
    "BATTERY": "电气",
    "CHILLER": "暖通",
    "SHU": "暖通",
    "COOLING_TOWER": "暖通",
    "COOLING_PUMP": "暖通",
    "WATER_SYSTEM": "暖通",
    "ROW_AC": "暖通",
    "MONITORING": "弱电",
    "ROOM_ENVIRONMENT": "机房环境",
    "TRANSMISSION": "IDC网络",
    "SERVER": "算力服务器",
    "MAINTENANCE_TOOL": "工器具",
}

HIGH_FREQUENCY = {
    "UPS_BATTERY",
    "SERVER_SSD",
    "SERVER_MEMORY",
    "SERVER_POWER_SUPPLY",
    "SERVER_FAN",
    "OPTICAL_TRANSCEIVER",
    "OPTICAL_FIBER",
    "ROOM_TEMP_HUMIDITY_SENSOR",
    "ROOM_WATER_LEAK_SENSOR",
    "UPS_FAN",
    "ROW_AC_FILTER",
    "SHU_FILTER",
    "PUMP_BEARING",
}
LOW_FREQUENCY = {
    "CHILLER_COMPRESSOR",
    "COOLING_TOWER_GEARBOX",
    "TRANSFORMER_PROTECTION_DEVICE",
    "HV_CIRCUIT_BREAKER",
}

CATEGORY_BRANDS = {
    "HV_SWITCHGEAR_10KV": ("Schneider", "ABB", "Siemens", "Chint"),
    "TRANSFORMER": ("Siemens", "ABB", "Schneider", "TBEA"),
    "LV_SWITCHGEAR_400V": ("Schneider", "ABB", "Siemens", "Chint"),
    "UPS": ("Huawei", "Vertiv", "Schneider", "Eaton"),
    "HVDC": ("Huawei", "Vertiv", "ZTE", "Delta"),
    "BATTERY": ("Narada", "Leoch", "Panasonic", "Sacred Sun"),
    "CHILLER": ("Carrier", "Trane", "York", "Daikin"),
    "SHU": ("Vertiv", "Stulz", "Schneider", "Rittal"),
    "COOLING_TOWER": ("Liangchi", "King Sun", "BAC", "Marley"),
    "COOLING_PUMP": ("Grundfos", "Wilo", "KSB", "CNP"),
    "WATER_SYSTEM": ("Siemens", "Honeywell", "Danfoss", "Belimo"),
    "ROW_AC": ("Vertiv", "Stulz", "Schneider", "Huawei"),
    "MONITORING": ("Honeywell", "Siemens", "Huawei", "Advantech"),
    "ROOM_ENVIRONMENT": ("Honeywell", "Siemens", "Sensaphone", "Raritan"),
    "TRANSMISSION": ("Huawei", "H3C", "Cisco", "FiberHome"),
    "SERVER": ("Dell", "HPE", "Lenovo", "Inspur", "Samsung", "Micron"),
    "MAINTENANCE_TOOL": ("Fluke", "Hioki", "UNI-T", "Keysight"),
}

BASE_PRICES = {
    "SERVER_GPU": 48000,
    "CHILLER_COMPRESSOR": 95000,
    "HV_CIRCUIT_BREAKER": 42000,
    "UPS_POWER_MODULE": 28000,
    "SERVER_CPU": 16000,
    "SERVER_SSD": 4200,
    "SERVER_MEMORY": 2800,
    "OPTICAL_TRANSCEIVER": 1800,
    "UPS_BATTERY": 1350,
    "PUMP_BEARING": 680,
    "ROOM_TEMP_HUMIDITY_SENSOR": 520,
}


@dataclass(frozen=True)
class PlannedItem:
    category_code: str
    canonical_item: str
    item_name: str
    product_index: int
    supplier_index: int
    quantity: int
    requires_warehouse: bool
    purchased_at: datetime
    unit_price: Decimal
    receipt_count: int
    delivery_days: int | None
    identity_mode: str


@dataclass(frozen=True)
class PlanSummary:
    purchase_requests: int
    purchase_items: int
    executions: int
    receipts: int
    suppliers: int
    equipment_models: int
    blacklists: int
    multi_item_request_ratio: float
    category_counts: dict[str, int]
    canonical_item_count: int
    recent_count: int
    stale_count: int
    split_receipt_executions: int


def _month_bucket_date(rng: random.Random, index: int, now: datetime) -> datetime:
    if index % 4:
        days_ago = rng.randint(5, 720)
    else:
        days_ago = rng.randint(731, 1680)
    return (now - timedelta(days=days_ago)).replace(hour=10 + index % 7, minute=0, second=0)


def _price_for(item: VocabularyItem, category: VocabularyCategory, index: int) -> Decimal:
    base = BASE_PRICES.get(item.canonical_item)
    if base is None:
        if any(token in item.canonical_item for token in ("COMPRESSOR", "GEARBOX", "BREAKER")):
            base = 24000
        elif any(token in item.canonical_item for token in ("MODULE", "BOARD", "MOTOR", "VFD")):
            base = 6800
        elif any(token in item.canonical_item for token in ("SENSOR", "FILTER", "FAN")):
            base = 850
        elif category.category_code == "MAINTENANCE_TOOL":
            base = 2200
        else:
            base = 1800
    supplier_factor = Decimal("0.92") + Decimal(index % 9) * Decimal("0.02")
    history_factor = Decimal("0.97") + Decimal(index % 7) * Decimal("0.01")
    return (Decimal(base) * supplier_factor * history_factor).quantize(Decimal("0.01"))


def _delivery_range(category_code: str) -> tuple[int, int]:
    if category_code in {"HV_SWITCHGEAR_10KV", "TRANSFORMER", "CHILLER", "COOLING_TOWER"}:
        return 7, 45
    if category_code in {"UPS", "HVDC", "LV_SWITCHGEAR_400V"}:
        return 3, 25
    if category_code in {"SERVER", "TRANSMISSION"}:
        return 2, 15
    return 1, 10


def _counts(count: int) -> dict[str, int]:
    if count < len(ALL_ITEMS) * 10:
        raise ValueError(
            f"count 必须至少为 {len(ALL_ITEMS) * 10}，才能覆盖每个 canonical item 10 条"
        )
    result = {item.canonical_item: 10 for _, item in ALL_ITEMS}
    weighted = [
        item.canonical_item
        for _, item in ALL_ITEMS
        for _ in range(
            4
            if item.canonical_item in HIGH_FREQUENCY
            else 1
            if item.canonical_item in LOW_FREQUENCY
            else 2
        )
    ]
    remaining = count - sum(result.values())
    for index in range(remaining):
        result[weighted[index % len(weighted)]] += 1
    return result


def build_plan(count: int, seed: int, now: datetime) -> tuple[list[PlannedItem], PlanSummary]:
    rng = random.Random(seed)
    target_counts = _counts(count)
    planned: list[PlannedItem] = []
    serial = 0
    for category, item in ALL_ITEMS:
        item_count = target_counts[item.canonical_item]
        names = (item.display_name, *item.aliases)
        for local_index in range(item_count):
            serial += 1
            purchased_at = _month_bucket_date(rng, serial, now)
            requires_warehouse = serial % 12 != 0
            has_receipt = requires_warehouse and serial % 9 != 0
            split_receipt = serial % 5 == 0 or serial % 13 == 0
            receipt_count = 0 if not has_receipt else 2 + serial % 2 if split_receipt else 1
            low, high = _delivery_range(category.category_code)
            delivery_days = rng.randint(low, high) if has_receipt else None
            identity_roll = local_index % 20
            identity_mode = (
                "MODEL" if identity_roll < 11 else "SNAPSHOT" if identity_roll < 17 else "GENERIC"
            )
            supplier_span = 12 if item.canonical_item in HIGH_FREQUENCY and local_index < 24 else 6
            product_index = (
                0 if item.canonical_item in HIGH_FREQUENCY and local_index < 12 else local_index % 4
            )
            supplier_index = local_index % supplier_span
            confidence_samples = {
                "SERVER_MEMORY": 7,
                "SERVER_POWER_SUPPLY": 5,
                "SERVER_FAN": 3,
            }
            if local_index < confidence_samples.get(item.canonical_item, 0):
                supplier_index = 5
            planned.append(
                PlannedItem(
                    category_code=category.category_code,
                    canonical_item=item.canonical_item,
                    item_name=names[local_index % len(names)],
                    product_index=product_index,
                    supplier_index=supplier_index,
                    quantity=1 + serial % 12,
                    requires_warehouse=requires_warehouse,
                    purchased_at=purchased_at,
                    unit_price=_price_for(item, category, serial),
                    receipt_count=receipt_count,
                    delivery_days=delivery_days,
                    identity_mode=identity_mode,
                )
            )
    rng.shuffle(planned)
    request_sizes: list[int] = []
    remaining = count
    pattern = (1, 2, 3, 4, 2, 3)
    while remaining:
        size = min(pattern[len(request_sizes) % len(pattern)], remaining)
        request_sizes.append(size)
        remaining -= size
    categories = Counter(row.category_code for row in planned)
    summary = PlanSummary(
        purchase_requests=len(request_sizes),
        purchase_items=len(planned),
        executions=len(planned),
        receipts=sum(row.receipt_count for row in planned),
        suppliers=SUPPLIER_COUNT,
        equipment_models=len(ALL_ITEMS) * 4,
        blacklists=6,
        multi_item_request_ratio=sum(size >= 2 for size in request_sizes) / len(request_sizes),
        category_counts=dict(sorted(categories.items())),
        canonical_item_count=len(target_counts),
        recent_count=sum(row.purchased_at >= now - timedelta(days=730) for row in planned),
        stale_count=sum(row.purchased_at < now - timedelta(days=730) for row in planned),
        split_receipt_executions=sum(row.receipt_count >= 2 for row in planned),
    )
    return planned, summary


def _safe_database() -> None:
    settings = get_settings()
    print(
        f"DB host={settings.mysql_host} port={settings.mysql_port} name={settings.mysql_database}"
    )
    if settings.mysql_host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("Task08 synthetic seed 只允许本机数据库")
    lowered = settings.mysql_database.lower()
    if any(token in lowered for token in ("prod", "production")):
        raise RuntimeError("数据库名称疑似 production，拒绝操作")


def _require_write_permission() -> None:
    if os.getenv("TASK08_ALLOW_SYNTHETIC_SEED") != "1":
        raise RuntimeError("实际写入或清理前必须设置 TASK08_ALLOW_SYNTHETIC_SEED=1")


def _supplier_rows() -> list[Supplier]:
    regions = ("南京", "苏州", "无锡", "常州", "扬州", "镇江")
    focuses = ("电气设备", "机电科技", "制冷技术", "数据系统", "通信技术", "环境监控")
    suffixes = ("服务", "工程", "供应链", "技术", "设备", "科技")
    rows = []
    for index in range(SUPPLIER_COUNT):
        name = (
            f"{regions[index % 6]}云枢{focuses[(index // 2) % 6]}"
            f"{suffixes[index % 6]}有限公司（合成）-{index + 1:02d}"
        )
        rows.append(
            Supplier(
                supplier_name=name,
                unified_social_credit_code=f"{CREDIT_PREFIX}{index + 1:04d}",
                bank_name=f"合成测试银行{index % 6 + 1}支行",
                bank_account=f"TESTBANK{index + 1:04d}000000",
                registered_address=f"{regions[index % 6]}市合成数据园区{index + 1}号",
                contract_contact_info=f"synthetic-contact-{index + 1:02d}",
                status=index >= 3,
            )
        )
    return rows


def _model_code(category: VocabularyCategory, item: VocabularyItem, product_index: int) -> str:
    stem = "".join(part[0] for part in item.canonical_item.split("_") if part)[:6]
    family = ("A", "E", "M", "X")[product_index]
    return f"{stem}-{family}{120 + product_index * 80}-{24 + product_index}"


def _device_profession(category_code: str) -> str:
    try:
        return DEVICE_PROFESSION_BY_CATEGORY[category_code]
    except KeyError as exc:
        raise RuntimeError(f"未配置设备专业映射: {category_code}") from exc


def _profession_by_database_category() -> dict[str, str]:
    result: dict[str, str] = {}
    for category in VOCABULARY:
        profession = _device_profession(category.category_code)
        existing = result.get(category.database_category_code)
        if existing is not None and existing != profession:
            raise RuntimeError(
                "数据库设备类别跨专业冲突: "
                f"{category.database_category_code} -> {existing}/{profession}"
            )
        result[category.database_category_code] = profession
    return result


async def repair_professions(*, dry_run: bool = False) -> dict[str, int]:
    _safe_database()
    if not dry_run:
        _require_write_permission()
    profession_by_category = _profession_by_database_category()
    async with async_session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(PurchaseRequest, EquipmentCategory.category_code)
                    .join(
                        PurchaseRequestItem,
                        PurchaseRequestItem.request_id == PurchaseRequest.request_id,
                    )
                    .join(
                        EquipmentCategory,
                        EquipmentCategory.category_id == PurchaseRequestItem.equipment_category_id,
                    )
                    .where(
                        PurchaseRequest.request_no.like(f"{REQUEST_PREFIX}%"),
                        PurchaseRequestItem.item_no == 1,
                    )
                )
            ).all()
        )
        unknown = sorted(
            {
                category_code
                for _, category_code in rows
                if category_code not in profession_by_category
            }
        )
        if unknown:
            raise RuntimeError(f"无法映射设备专业的数据库类别: {unknown}")
        changed = [
            (request, profession_by_category[category_code])
            for request, category_code in rows
            if request.device_profession != profession_by_category[category_code]
        ]
        counts = {"requests": len(rows), "changed": len(changed)}
        if not dry_run:
            for request, profession in changed:
                request.device_profession = profession
            await session.commit()
        print(json.dumps(counts, ensure_ascii=False, indent=2))
        return counts


async def repair_catalog_and_suppliers(*, dry_run: bool = False) -> dict[str, int]:
    _safe_database()
    if not dry_run:
        _require_write_permission()
    async with async_session_factory() as session:
        items = list(
            (
                await session.scalars(
                    select(PurchaseRequestItem)
                    .join(PurchaseRequest)
                    .where(PurchaseRequest.request_no.like(f"{REQUEST_PREFIX}%"))
                )
            ).all()
        )
        models = {
            row.model_id: row
            for row in (
                await session.scalars(
                    select(EquipmentModel).where(EquipmentModel.remark == BATCH_MARKER)
                )
            ).all()
        }
        changed_items = []
        for item in items:
            model = models.get(item.equipment_model_id)
            if model is None:
                candidates = [
                    row
                    for row in models.values()
                    if row.category_id == item.equipment_category_id
                    and (
                        item.item_name in row.model_name
                        or (
                            item.remark
                            and row.specifications.get("canonical_item")
                            == item.remark.split("canonical_item=", 1)[-1]
                        )
                    )
                ]
                if not candidates:
                    raise RuntimeError(f"无法为合成采购项匹配产品目录: {item.request_item_id}")
                model = candidates[0]
            if (
                item.equipment_model_id != model.model_id
                or item.brand_snapshot != model.brand
                or item.model_snapshot != model.model
            ):
                item.equipment_model_id = model.model_id
                item.brand_snapshot = model.brand
                item.model_snapshot = model.model
                changed_items.append(item)

        suppliers = list(
            (
                await session.scalars(
                    select(Supplier).where(
                        Supplier.unified_social_credit_code.like(f"{CREDIT_PREFIX}%")
                    )
                )
            ).all()
        )
        changed_suppliers = []
        for index, supplier in enumerate(
            sorted(suppliers, key=lambda row: row.unified_social_credit_code)
        ):
            expected_name = f"合成测试银行{index % 6 + 1}支行"
            expected_account = f"TESTBANK{index + 1:04d}000000"
            if supplier.bank_name != expected_name or supplier.bank_account != expected_account:
                supplier.bank_name = expected_name
                supplier.bank_account = expected_account
                changed_suppliers.append(supplier)
        counts = {
            "items": len(items),
            "changed_items": len(changed_items),
            "suppliers": len(suppliers),
            "changed_suppliers": len(changed_suppliers),
        }
        if not dry_run:
            await session.commit()
        print(json.dumps(counts, ensure_ascii=False, indent=2))
        return counts


async def _existing_master_data(session):
    categories = {
        row.category_code: row for row in (await session.scalars(select(EquipmentCategory))).all()
    }
    buildings = list(
        (
            await session.scalars(
                select(Building).where(Building.status.is_(True)).order_by(Building.building_id)
            )
        ).all()
    )
    employees = list(
        (
            await session.scalars(
                select(Employee).where(Employee.status.is_(True)).order_by(Employee.employee_id)
            )
        ).all()
    )
    missing = [
        category.database_category_code
        for category in VOCABULARY
        if category.database_category_code not in categories
    ]
    if missing:
        raise RuntimeError(f"数据库缺少 Vocabulary 对应类别: {missing}")
    if not buildings or len(employees) < 4:
        raise RuntimeError("数据库缺少可复用 building/employee 主数据")
    return categories, buildings, employees


async def cleanup(*, dry_run: bool = False) -> dict[str, int]:
    _safe_database()
    if not dry_run:
        _require_write_permission()
    async with async_session_factory() as session:
        request_ids = list(
            (
                await session.scalars(
                    select(PurchaseRequest.request_id).where(
                        PurchaseRequest.request_no.like(f"{REQUEST_PREFIX}%")
                    )
                )
            ).all()
        )
        model_ids = list(
            (
                await session.scalars(
                    select(EquipmentModel.model_id).where(EquipmentModel.remark == BATCH_MARKER)
                )
            ).all()
        )
        supplier_ids = list(
            (
                await session.scalars(
                    select(Supplier.supplier_id).where(
                        Supplier.unified_social_credit_code.like(f"{CREDIT_PREFIX}%")
                    )
                )
            ).all()
        )
        counts = {
            "requests": len(request_ids),
            "models": len(model_ids),
            "suppliers": len(supplier_ids),
        }
        if dry_run:
            print(json.dumps(counts, ensure_ascii=False, indent=2))
            return counts
        if request_ids:
            await session.execute(
                delete(WarehouseReceipt).where(WarehouseReceipt.request_id.in_(request_ids))
            )
            await session.execute(
                delete(SupplierBlacklist).where(
                    SupplierBlacklist.source_request_id.in_(request_ids)
                )
            )
            await session.execute(
                delete(PurchaseExecution).where(PurchaseExecution.request_id.in_(request_ids))
            )
            await session.execute(
                delete(PurchaseRequestItem).where(PurchaseRequestItem.request_id.in_(request_ids))
            )
            await session.execute(
                delete(PurchaseRequest).where(PurchaseRequest.request_id.in_(request_ids))
            )
        if model_ids:
            await session.execute(
                delete(EquipmentModel).where(EquipmentModel.model_id.in_(model_ids))
            )
        if supplier_ids:
            await session.execute(delete(Supplier).where(Supplier.supplier_id.in_(supplier_ids)))
        await session.commit()
        if MANIFEST_PATH.exists():
            MANIFEST_PATH.unlink()
        print(f"cleanup complete: {counts}")
        return counts


async def seed(count: int, seed_value: int) -> dict[str, object]:
    _safe_database()
    _require_write_permission()
    now = datetime.now().replace(microsecond=0)
    planned, summary = build_plan(count, seed_value, now)
    if summary.purchase_items != count:
        raise RuntimeError("计划 PurchaseRequestItem 数量不等于请求数量")
    await cleanup(dry_run=False)
    manifest: dict[str, object] = {
        "marker": BATCH_MARKER,
        "seed": seed_value,
        "summary": asdict(summary),
    }
    async with async_session_factory() as session:
        categories, buildings, employees = await _existing_master_data(session)
        applicant, purchaser, warehouse, registrar = employees[:4]
        suppliers = _supplier_rows()
        session.add_all(suppliers)
        await session.flush()
        models: dict[tuple[str, str, int], EquipmentModel] = {}
        for category, vocab_item in ALL_ITEMS:
            db_category = categories[category.database_category_code]
            brands = CATEGORY_BRANDS[category.category_code]
            for product_index in range(4):
                model = EquipmentModel(
                    category_id=db_category.category_id,
                    brand=brands[product_index % len(brands)],
                    model=_model_code(category, vocab_item, product_index),
                    model_name=f"{vocab_item.display_name} {product_index + 1}型（合成）",
                    specifications={"canonical_item": vocab_item.canonical_item, "synthetic": True},
                    default_unit="件",
                    lifecycle_status="ACTIVE",
                    remark=BATCH_MARKER,
                )
                session.add(model)
                models[(category.category_code, vocab_item.canonical_item, product_index)] = model
        await session.flush()
        request_ids: list[int] = []
        item_ids: list[int] = []
        execution_ids: list[int] = []
        receipt_ids: list[int] = []
        cursor = 0
        request_index = 0
        pattern = (1, 2, 3, 4, 2, 3)
        while cursor < len(planned):
            request_index += 1
            size = min(pattern[(request_index - 1) % len(pattern)], len(planned) - cursor)
            chunk = planned[cursor : cursor + size]
            cursor += size
            request = PurchaseRequest(
                request_no=f"{REQUEST_PREFIX}{seed_value}-{request_index:04d}",
                building_id=buildings[0].building_id,
                request_type="PURCHASE",
                applicant_employee_id=applicant.employee_id,
                applicant_platform_type_snapshot="SYNTHETIC",
                applicant_platform_user_id_snapshot="task08-seeder",
                applicant_name_snapshot=applicant.name,
                device_profession=_device_profession(chunk[0].category_code),
                device_name=chunk[0].item_name,
                quantity=Decimal(str(sum(row.quantity for row in chunk))),
                unit="项",
                application_reason="Task08 推荐核心合成历史数据",
                applicant_remark=BATCH_MARKER,
                status="COMPLETED",
                version=1,
                submitted_at=min(row.purchased_at for row in chunk) - timedelta(days=2),
                completed_at=max(row.purchased_at for row in chunk) + timedelta(days=50),
            )
            session.add(request)
            await session.flush()
            request_ids.append(request.request_id)
            for item_no, row in enumerate(chunk, start=1):
                category = next(
                    value for value in VOCABULARY if value.category_code == row.category_code
                )
                vocab_item = next(
                    value for value in category.items if value.canonical_item == row.canonical_item
                )
                model = models[(row.category_code, row.canonical_item, row.product_index)]
                use_model_id = True
                use_snapshot = True
                request_item = PurchaseRequestItem(
                    request_id=request.request_id,
                    item_no=item_no,
                    item_kind="COMPONENT",
                    equipment_category_id=categories[category.database_category_code].category_id,
                    equipment_model_id=model.model_id if use_model_id else None,
                    item_name=row.item_name,
                    brand_snapshot=model.brand if use_snapshot else None,
                    model_snapshot=model.model if use_snapshot else None,
                    quantity=Decimal(row.quantity),
                    unit="件",
                    requires_warehouse=row.requires_warehouse,
                    item_reason="Task08 synthetic recommendation history",
                    is_active=True,
                    remark=f"{BATCH_MARKER};canonical_item={vocab_item.canonical_item}",
                )
                session.add(request_item)
                await session.flush()
                item_ids.append(request_item.request_item_id)
                compatible_suppliers = [
                    supplier
                    for index, supplier in enumerate(suppliers)
                    if index % len(VOCABULARY)
                    in {
                        list(VOCABULARY).index(category),
                        (list(VOCABULARY).index(category) + 1) % len(VOCABULARY),
                        (list(VOCABULARY).index(category) + 5) % len(VOCABULARY),
                    }
                ]
                if len(compatible_suppliers) < 12:
                    compatible_suppliers = suppliers
                supplier = compatible_suppliers[row.supplier_index % len(compatible_suppliers)]
                total_price = row.unit_price * Decimal(row.quantity)
                execution = PurchaseExecution(
                    request_id=request.request_id,
                    request_item_id=request_item.request_item_id,
                    purchaser_employee_id=purchaser.employee_id,
                    purchaser_platform_type_snapshot="SYNTHETIC",
                    purchaser_platform_user_id_snapshot="task08-seeder",
                    purchaser_name_snapshot=purchaser.name,
                    supplier_id=supplier.supplier_id,
                    supplier_name_snapshot=supplier.supplier_name,
                    supplier_tax_no_snapshot=supplier.unified_social_credit_code,
                    actual_unit_price=row.unit_price,
                    purchased_quantity=Decimal(row.quantity),
                    actual_total_price=total_price,
                    purchased_at=row.purchased_at,
                    execution_remark=f"{BATCH_MARKER};canonical_item={row.canonical_item}",
                )
                session.add(execution)
                await session.flush()
                execution_ids.append(execution.execution_id)
                if row.receipt_count and row.delivery_days is not None:
                    remaining_quantity = Decimal(row.quantity)
                    for receipt_index in range(row.receipt_count):
                        receipt_quantity = (
                            remaining_quantity
                            if receipt_index == row.receipt_count - 1
                            else (Decimal(row.quantity) / Decimal(row.receipt_count)).quantize(
                                Decimal("0.001")
                            )
                        )
                        remaining_quantity -= receipt_quantity
                        delivery_fraction = Decimal(receipt_index + 1) / Decimal(row.receipt_count)
                        received_at = row.purchased_at + timedelta(
                            days=max(1, int(Decimal(row.delivery_days) * delivery_fraction))
                        )
                        receipt = WarehouseReceipt(
                            request_id=request.request_id,
                            execution_id=execution.execution_id,
                            warehouse_employee_id=warehouse.employee_id,
                            warehouse_platform_type_snapshot="SYNTHETIC",
                            warehouse_platform_user_id_snapshot="task08-seeder",
                            warehouse_name_snapshot=warehouse.name,
                            warehouse_location="Task08 合成入库区",
                            received_quantity=receipt_quantity,
                            receipt_remark=BATCH_MARKER,
                            received_at=received_at,
                        )
                        session.add(receipt)
                        await session.flush()
                        receipt_ids.append(receipt.receipt_id)
        blacklist_specs = (
            (0, "ACTIVE", "PERMANENT", None, None),
            (1, "ACTIVE", "LIMITED", now + timedelta(days=180), None),
            (2, "RELEASED", "PERMANENT", None, now - timedelta(days=30)),
            (3, "RELEASED", "LIMITED", now + timedelta(days=30), now - timedelta(days=10)),
            (4, "ACTIVE", "LIMITED", now - timedelta(days=1), None),
            (5, "RELEASED", "LIMITED", now - timedelta(days=200), now - timedelta(days=190)),
        )
        blacklist_ids = []
        for supplier_index, status, duration_type, end_at, released_at in blacklist_specs:
            supplier = suppliers[supplier_index]
            blacklist = SupplierBlacklist(
                supplier_id=supplier.supplier_id,
                supplier_name_snapshot=supplier.supplier_name,
                source_request_id=request_ids[supplier_index],
                registrar_employee_id=registrar.employee_id,
                registrar_platform_type_snapshot="SYNTHETIC",
                registrar_platform_user_id_snapshot="task08-seeder",
                registrar_name_snapshot=registrar.name,
                blacklist_type="合成履约场景",
                blacklist_reason=f"{BATCH_MARKER} recommendation hard-filter scenario",
                duration_type=duration_type,
                start_at=now - timedelta(days=365),
                end_at=end_at,
                released_at=released_at,
                released_by_employee_id=registrar.employee_id if released_at else None,
                release_reason="合成解除场景" if released_at else None,
                status=status,
            )
            session.add(blacklist)
            await session.flush()
            blacklist_ids.append(blacklist.blacklist_id)
        await session.commit()
        manifest.update(
            {
                "purchase_request_ids": request_ids,
                "request_item_ids": item_ids,
                "execution_ids": execution_ids,
                "receipt_ids": receipt_ids,
                "supplier_ids": [row.supplier_id for row in suppliers],
                "equipment_model_ids": [row.model_id for row in models.values()],
                "blacklist_ids": blacklist_ids,
            }
        )
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2, default=str))
    print(f"manifest={MANIFEST_PATH}")
    return manifest


def dry_run(count: int, seed_value: int) -> PlanSummary:
    _safe_database()
    _, summary = build_plan(count, seed_value, datetime.now().replace(microsecond=0))
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2, default=str))
    if len(summary.category_counts) != 17 or summary.canonical_item_count != len(ALL_ITEMS):
        raise RuntimeError("Vocabulary 覆盖不完整")
    return summary


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=TOTAL_PURCHASE_ITEMS)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--repair-professions", action="store_true")
    parser.add_argument("--repair-catalog-and-suppliers", action="store_true")
    args = parser.parse_args()
    try:
        if args.cleanup:
            await cleanup(dry_run=args.dry_run)
        elif args.repair_professions:
            await repair_professions(dry_run=args.dry_run)
        elif args.repair_catalog_and_suppliers:
            await repair_catalog_and_suppliers(dry_run=args.dry_run)
        elif args.dry_run:
            dry_run(args.count, args.seed)
        else:
            await seed(args.count, args.seed)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
