from pydantic import BaseModel, ConfigDict

from procurement_platform.domain.enums import RoleCode


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UserRole(DomainModel):
    role_code: RoleCode
    role_name: str | None = None


class UserBuilding(DomainModel):
    building_id: int
    building_name: str
    is_primary: bool = False


class CurrentUser(DomainModel):
    employee_id: int
    name: str
    mobile: str | None
    status: str
    roles: tuple[UserRole, ...]
    buildings: tuple[UserBuilding, ...]
