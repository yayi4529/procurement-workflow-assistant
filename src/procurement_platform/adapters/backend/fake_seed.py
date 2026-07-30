import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.requirement import (
    HandlerCandidate,
    SupplierBlacklistSummary,
    SupplierDetail,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


class FakeBuildingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    building_id: int = Field(gt=0)
    building_name: str = Field(min_length=1)
    is_primary: bool = False


class FakeUserConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    platform_user_id: str = Field(min_length=1)
    employee_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    roles: tuple[RoleCode, ...] = Field(min_length=1)
    buildings: tuple[FakeBuildingConfig, ...] = ()


class FakeHandlerRoutingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    building_manager_by_building: dict[int, tuple[int, ...]]
    purchasers: tuple[int, ...]
    warehouse_managers: tuple[int, ...]


class FakeSupplierConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    supplier_id: int = Field(gt=0)
    supplier_name: str = Field(min_length=1)
    supplier_tax_number: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    registered_address: str | None = None
    contract_contact_info: str | None = None


class FakeBackendSeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    users: tuple[FakeUserConfig, ...] = Field(min_length=1)
    routing: FakeHandlerRoutingConfig
    suppliers: tuple[FakeSupplierConfig, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> "FakeBackendSeedConfig":
        open_ids = [item.platform_user_id for item in self.users]
        employee_ids = [item.employee_id for item in self.users]
        supplier_ids = [item.supplier_id for item in self.suppliers]
        if len(open_ids) != len(set(open_ids)):
            raise ValueError("platform_user_id must be unique")
        if len(employee_ids) != len(set(employee_ids)):
            raise ValueError("employee_id must be unique")
        if len(supplier_ids) != len(set(supplier_ids)):
            raise ValueError("supplier_id must be unique")
        users = {item.employee_id: item for item in self.users}
        for building_id, candidates in self.routing.building_manager_by_building.items():
            for employee_id in candidates:
                user = self._candidate(users, employee_id, RoleCode.BUILDING_MANAGER)
                if building_id not in {item.building_id for item in user.buildings}:
                    raise ValueError("building manager must belong to the routed building")
        for employee_id in self.routing.purchasers:
            self._candidate(users, employee_id, RoleCode.PURCHASER)
        for employee_id in self.routing.warehouse_managers:
            self._candidate(users, employee_id, RoleCode.WAREHOUSE_MANAGER)
        return self

    @staticmethod
    def _candidate(
        users: dict[int, FakeUserConfig], employee_id: int, role: RoleCode
    ) -> FakeUserConfig:
        user = users.get(employee_id)
        if user is None:
            raise ValueError(f"routing references unknown employee_id {employee_id}")
        if role not in user.roles:
            raise ValueError(f"routing employee_id {employee_id} does not have role {role}")
        return user


class FakeBackendSeedLoader:
    @staticmethod
    def load(path: str | Path) -> FakeBackendSeedConfig:
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"fake seed file not found: {source}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"fake seed file is not valid JSON: {source}") from exc
        try:
            return FakeBackendSeedConfig.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"fake seed validation failed: {exc}") from exc

    @staticmethod
    def users(seed: FakeBackendSeedConfig) -> dict[str, CurrentUser]:
        return {
            item.platform_user_id: CurrentUser(
                employee_id=item.employee_id,
                name=item.name,
                mobile=None,
                status="ACTIVE",
                roles=tuple(UserRole(role_code=role) for role in item.roles),
                buildings=tuple(
                    UserBuilding(**building.model_dump()) for building in item.buildings
                ),
            )
            for item in seed.users
        }

    @staticmethod
    def candidates(seed: FakeBackendSeedConfig) -> tuple[HandlerCandidate, ...]:
        employee_ids = {
            employee_id
            for values in seed.routing.building_manager_by_building.values()
            for employee_id in values
        }
        employee_ids.update(seed.routing.purchasers)
        employee_ids.update(seed.routing.warehouse_managers)
        users = {item.employee_id: item for item in seed.users}
        return tuple(
            HandlerCandidate(employee_id=employee_id, name=users[employee_id].name)
            for employee_id in sorted(employee_ids)
        )

    @staticmethod
    def candidates_by_role(
        seed: FakeBackendSeedConfig,
    ) -> dict[RoleCode, tuple[HandlerCandidate, ...]]:
        users = {item.employee_id: item for item in seed.users}
        manager_ids = {
            employee_id
            for values in seed.routing.building_manager_by_building.values()
            for employee_id in values
        }
        role_ids = {
            RoleCode.BUILDING_MANAGER: manager_ids,
            RoleCode.PURCHASER: set(seed.routing.purchasers),
            RoleCode.WAREHOUSE_MANAGER: set(seed.routing.warehouse_managers),
        }
        return {
            role: tuple(
                HandlerCandidate(employee_id=employee_id, name=users[employee_id].name)
                for employee_id in sorted(employee_ids)
            )
            for role, employee_ids in role_ids.items()
        }

    @staticmethod
    def suppliers(seed: FakeBackendSeedConfig) -> tuple[SupplierDetail, ...]:
        return tuple(
            SupplierDetail(
                supplier_id=item.supplier_id,
                supplier_name=item.supplier_name,
                supplier_tax_number=item.supplier_tax_number,
                bank_name=item.bank_name,
                bank_account=item.bank_account,
                registered_address=item.registered_address,
                contract_contact_info=item.contract_contact_info,
                bank_account_masked=False,
                blacklist=SupplierBlacklistSummary(active=False),
            )
            for item in seed.suppliers
        )
