from uuid import UUID

from pydantic import BaseModel, ConfigDict

from procurement_platform.domain.enums import AllowedRequirementAction, RequirementStatus


class RequirementModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RequirementBuilding(RequirementModel):
    building_id: int
    building_name: str


class RequirementHandler(RequirementModel):
    employee_id: int
    name: str


class ApplicantFields(RequirementModel):
    device_profession: str | None = None
    device_name: str | None = None
    brand: str | None = None
    model: str | None = None
    quantity: str | None = None
    unit: str | None = None
    application_reason: str | None = None
    applicant_remark: str | None = None


class ApplicantFieldsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_profession: str | None = None
    device_name: str | None = None
    brand: str | None = None
    model: str | None = None
    quantity: str | None = None
    unit: str | None = None
    application_reason: str | None = None
    applicant_remark: str | None = None

    def provided_fields(self) -> dict[str, str | None]:
        return self.model_dump(exclude_unset=True)


class RequirementSummary(RequirementModel):
    requirement_id: int
    requirement_no: str
    status: RequirementStatus
    version: int


class ApplicantFieldsSaveResult(RequirementModel):
    requirement_id: int
    status: RequirementStatus
    version: int
    missing_fields: tuple[str, ...]
    next_missing_field: str | None
    fields_complete: bool


class RequirementDetail(RequirementSummary):
    building: RequirementBuilding
    current_handler: RequirementHandler | None = None
    applicant_fields: ApplicantFields
    missing_fields: tuple[str, ...]
    allowed_actions: tuple[AllowedRequirementAction, ...]
    fields_complete: bool = False
    rejection_reason: str | None = None


class RequirementListItem(RequirementSummary):
    device_name: str | None = None
    current_handler: RequirementHandler | None = None


class RequirementPage(RequirementModel):
    items: tuple[RequirementListItem, ...]
    page: int
    page_size: int
    total: int


class HandlerCandidate(RequirementModel):
    employee_id: int
    name: str


class HandlerCandidates(RequirementModel):
    items: tuple[HandlerCandidate, ...]
    auto_selected_employee_id: int | None = None


class RequirementTransitionResult(RequirementSummary):
    current_handler: RequirementHandler | None = None
    action_token: UUID | None = None
