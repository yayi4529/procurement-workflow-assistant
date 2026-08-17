"""Create only the local development employees needed for Feishu HTTP integration.

This intentionally does not create procurement requests, suppliers, identities, or
any other demo data. Run the identity binding script afterwards.
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
from app.models.identity import Building, Employee, EmployeeBuilding, EmployeeRole, Role


@dataclass(frozen=True, slots=True)
class TestEmployee:
    employee_id: int
    employee_no: str
    name: str
    mobile: str
    role_code: str
    building_id: int | None


TEST_EMPLOYEES = (
    TestEmployee(90001, "TEST-E001", "测试需求人", "13800009001", "APPLICANT", 1),
    TestEmployee(90002, "TEST-E002", "测试一号楼楼长", "13800009002", "BUILDING_MANAGER", 1),
    TestEmployee(90003, "TEST-E003", "测试采购员", "13800009003", "PURCHASER", None),
    TestEmployee(90004, "TEST-E004", "测试仓库管理员", "13800009004", "WAREHOUSE_MANAGER", None),
)


class BootstrapError(RuntimeError):
    """The local bootstrap data could not be safely established."""


def validate_local_development_settings() -> None:
    settings = get_settings()
    if settings.app_env.lower() != "development":
        raise BootstrapError("refusing to run outside APP_ENV=development")
    if settings.mysql_host != "127.0.0.1" or settings.mysql_port != 3307:
        raise BootstrapError("refusing to run outside MySQL 127.0.0.1:3307")
    if settings.mysql_database != "procurement_agent":
        raise BootstrapError("refusing to run outside database procurement_agent")


async def require_role(session: AsyncSession, role_code: str) -> int:
    role = await session.scalar(
        select(Role).where(Role.role_code == role_code, Role.status.is_(True))
    )
    if role is None:
        raise BootstrapError(f"ACTIVE_ROLE_NOT_FOUND role_code={role_code}")
    return role.role_id


async def require_building(session: AsyncSession, building_id: int) -> None:
    building = await session.scalar(
        select(Building).where(Building.building_id == building_id, Building.status.is_(True))
    )
    if building is None:
        raise BootstrapError(f"ACTIVE_BUILDING_NOT_FOUND building_id={building_id}")


async def bootstrap_employee(session: AsyncSession, item: TestEmployee, *, apply: bool) -> str:
    role_id = await require_role(session, item.role_code)
    if item.building_id is not None:
        await require_building(session, item.building_id)

    employee = await session.scalar(
        select(Employee).where(Employee.employee_id == item.employee_id)
    )
    if employee is None:
        if apply:
            session.add(
                Employee(
                    employee_id=item.employee_id,
                    employee_no=item.employee_no,
                    name=item.name,
                    mobile=item.mobile,
                    status=True,
                )
            )
            await session.flush()
        employee_action = "inserted"
    else:
        if (
            employee.employee_no != item.employee_no
            or employee.name != item.name
            or employee.mobile != item.mobile
            or not employee.status
        ):
            raise BootstrapError(f"EMPLOYEE_CONFLICT employee_id={item.employee_id}")
        employee_action = "unchanged"

    assignment = await session.scalar(
        select(EmployeeRole).where(
            EmployeeRole.employee_id == item.employee_id,
            EmployeeRole.role_id == role_id,
        )
    )
    if assignment is None:
        if apply:
            session.add(
                EmployeeRole(
                    employee_id=item.employee_id,
                    role_id=role_id,
                    status=True,
                    synced_at=datetime.now(),
                )
            )
        role_action = "assigned"
    elif assignment.status:
        role_action = "unchanged"
    else:
        raise BootstrapError(f"INACTIVE_ROLE_ASSIGNMENT employee_id={item.employee_id}")

    building_action = "not_applicable"
    if item.building_id is not None:
        assignment = await session.scalar(
            select(EmployeeBuilding).where(
                EmployeeBuilding.employee_id == item.employee_id,
                EmployeeBuilding.building_id == item.building_id,
            )
        )
        if assignment is None:
            if apply:
                session.add(
                    EmployeeBuilding(
                        employee_id=item.employee_id,
                        building_id=item.building_id,
                        is_primary=True,
                        status=True,
                        synced_at=datetime.now(),
                    )
                )
            building_action = "assigned"
        elif assignment.status:
            building_action = "unchanged"
        else:
            raise BootstrapError(f"INACTIVE_BUILDING_ASSIGNMENT employee_id={item.employee_id}")

    return f"employee={employee_action} role={role_action} building={building_action}"


async def run(*, apply: bool) -> None:
    validate_local_development_settings()
    async with async_session_factory() as session:
        if apply:
            async with session.begin():
                for item in TEST_EMPLOYEES:
                    result = await bootstrap_employee(session, item, apply=True)
                    print(f"APPLY employee {item.employee_id} {item.role_code}: {result}")
        else:
            for item in TEST_EMPLOYEES:
                result = await bootstrap_employee(session, item, apply=False)
                print(f"PLAN employee {item.employee_id} {item.role_code}: {result}")
            print("No changes were written.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate without writing (default).")
    parser.add_argument(
        "--apply", action="store_true", help="Create missing test records atomically."
    )
    arguments = parser.parse_args()
    if arguments.check and arguments.apply:
        parser.error("choose only one of --check or --apply")
    asyncio.run(run(apply=arguments.apply))


if __name__ == "__main__":
    try:
        main()
    except BootstrapError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1) from error
