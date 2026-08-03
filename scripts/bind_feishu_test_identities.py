"""Bind the four local FEISHU test identities to seeded development employees.

This script is intentionally limited to the local development database.  It does
not create employees, roles, or building assignments, and it never deletes or
replaces existing identities.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.identity import (
    Employee,
    EmployeeBuilding,
    EmployeeExternalIdentity,
    EmployeeRole,
    Role,
)

PLATFORM_TYPE = "FEISHU"


@dataclass(frozen=True, slots=True)
class Binding:
    employee_id: int
    role_code: str
    building_id: int | None
    platform_user_id: str
    label: str


BINDINGS = (
    Binding(90001, "APPLICANT", 1, "ou_3da4d0e3765ebe815eae094a70e0ca8d", "测试需求人"),
    Binding(90002, "BUILDING_MANAGER", 1, "ou_1b706cd21f22664d8d8543300907f8c2", "测试一号楼楼长"),
    Binding(90003, "PURCHASER", None, "ou_ea5a26a5072babe56a67ba7f79a04cea", "测试采购员"),
    Binding(
        90004, "WAREHOUSE_MANAGER", None, "ou_181fb1f4d15a557abca07402af468c18", "测试仓库管理员"
    ),
)


class BindingError(RuntimeError):
    """A safety validation or binding conflict prevented a write."""


def validate_local_development_settings() -> None:
    settings = get_settings()
    if settings.app_env.lower() != "development":
        raise BindingError("refusing to run outside APP_ENV=development")
    if settings.mysql_host != "127.0.0.1":
        raise BindingError("refusing to run unless MYSQL_HOST is exactly 127.0.0.1")
    if settings.mysql_port != 3307:
        raise BindingError("refusing to run unless MYSQL_PORT is 3307")
    if settings.mysql_database != "procurement_agent":
        raise BindingError("refusing to run unless MYSQL_DATABASE is procurement_agent")


async def validate_employee(session: AsyncSession, binding: Binding) -> None:
    employee = await session.scalar(
        select(Employee).where(Employee.employee_id == binding.employee_id)
    )
    if employee is None:
        raise BindingError(f"EMPLOYEE_NOT_FOUND employee_id={binding.employee_id}")
    if not employee.status:
        raise BindingError(f"EMPLOYEE_INACTIVE employee_id={binding.employee_id}")

    role = await session.scalar(
        select(Role.role_id)
        .join(EmployeeRole, EmployeeRole.role_id == Role.role_id)
        .where(
            EmployeeRole.employee_id == binding.employee_id,
            EmployeeRole.status.is_(True),
            Role.status.is_(True),
            Role.role_code == binding.role_code,
        )
    )
    if role is None:
        raise BindingError(
            f"ROLE_MISMATCH employee_id={binding.employee_id} expected={binding.role_code}"
        )

    if binding.building_id is not None:
        building = await session.scalar(
            select(EmployeeBuilding.employee_id).where(
                EmployeeBuilding.employee_id == binding.employee_id,
                EmployeeBuilding.building_id == binding.building_id,
                EmployeeBuilding.status.is_(True),
            )
        )
        if building is None:
            raise BindingError(
                "BUILDING_MISMATCH "
                f"employee_id={binding.employee_id} expected_building_id={binding.building_id}"
            )


async def plan_binding(
    session: AsyncSession, binding: Binding
) -> tuple[str, EmployeeExternalIdentity | None]:
    existing_open_id = await session.scalar(
        select(EmployeeExternalIdentity).where(
            EmployeeExternalIdentity.platform_type == PLATFORM_TYPE,
            EmployeeExternalIdentity.platform_user_id == binding.platform_user_id,
        )
    )
    if existing_open_id is not None and existing_open_id.employee_id != binding.employee_id:
        raise BindingError(
            "CONFLICT_OPEN_ID_BOUND_TO_OTHER_EMPLOYEE "
            f"open_id={binding.platform_user_id} employee_id={existing_open_id.employee_id}"
        )

    active_identity = await session.scalar(
        select(EmployeeExternalIdentity).where(
            EmployeeExternalIdentity.employee_id == binding.employee_id,
            EmployeeExternalIdentity.platform_type == PLATFORM_TYPE,
            EmployeeExternalIdentity.status.is_(True),
        )
    )
    if active_identity is not None and active_identity.platform_user_id != binding.platform_user_id:
        raise BindingError(
            "CONFLICT_EMPLOYEE_ALREADY_HAS_ACTIVE_FEISHU_IDENTITY "
            f"employee_id={binding.employee_id} open_id={active_identity.platform_user_id}"
        )

    if existing_open_id is None:
        return "inserted", None
    if existing_open_id.status:
        return "refreshed", existing_open_id
    return "reactivated", existing_open_id


async def check_bindings(
    session: AsyncSession,
) -> list[tuple[Binding, str, EmployeeExternalIdentity | None]]:
    plans: list[tuple[Binding, str, EmployeeExternalIdentity | None]] = []
    for binding in BINDINGS:
        await validate_employee(session, binding)
        action, identity = await plan_binding(session, binding)
        plans.append((binding, action, identity))
    return plans


async def run(*, apply: bool) -> None:
    validate_local_development_settings()
    settings = get_settings()
    print(f"environment: {settings.app_env}")
    print(f"database host: {settings.mysql_host}")
    print(f"database port: {settings.mysql_port}")
    print(f"database name: {settings.mysql_database}")

    async with async_session_factory() as session:
        if not apply:
            plans = await check_bindings(session)
            for binding, action, _ in plans:
                building = f" building {binding.building_id}" if binding.building_id else ""
                print(
                    f"PASS employee {binding.employee_id} {binding.role_code}{building}; "
                    f"PLAN {action} {PLATFORM_TYPE} {binding.platform_user_id}"
                )
            print("No changes were written.")
            return

        async with session.begin():
            plans = await check_bindings(session)
            now = datetime.now()
            for binding, action, identity in plans:
                if identity is None:
                    session.add(
                        EmployeeExternalIdentity(
                            employee_id=binding.employee_id,
                            platform_type=PLATFORM_TYPE,
                            platform_user_id=binding.platform_user_id,
                            status=True,
                            last_synced_at=now,
                        )
                    )
                else:
                    identity.status = True
                    identity.last_synced_at = now
                print(
                    f"APPLY {action} employee {binding.employee_id} "
                    f"{PLATFORM_TYPE} {binding.platform_user_id}"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate without writing (default).")
    parser.add_argument(
        "--apply", action="store_true", help="Validate and write bindings atomically."
    )
    arguments = parser.parse_args()
    if arguments.check and arguments.apply:
        parser.error("choose only one of --check or --apply")
    asyncio.run(run(apply=arguments.apply))


if __name__ == "__main__":
    try:
        main()
    except BindingError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1) from error
