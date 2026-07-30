from uuid import UUID

import pytest
from pydantic import ValidationError

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.warehouse.workflow_service import WarehouseWorkflowService
from procurement_platform.domain.enums import (
    AllowedRequirementAction,
    PlatformType,
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ApplicantFields,
    PurchaseFields,
    RequirementBuilding,
    RequirementDetail,
    RequirementHandler,
    WarehouseFieldsPatch,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def identity() -> PlatformIdentity:
    return PlatformIdentity(PlatformType.TEST_PLATFORM, "ou_warehouse", "request")


def backend(quantity: str = "2") -> FakeBackendClient:
    fake = FakeBackendClient(
        CurrentUser(
            employee_id=12,
            name="仓库管理员",
            mobile=None,
            status="ACTIVE",
            roles=(UserRole(role_code=RoleCode.WAREHOUSE_MANAGER),),
            buildings=(UserBuilding(building_id=1, building_name="一号楼"),),
        )
    )
    fake.seed_requirement(
        RequirementDetail(
            requirement_id=1,
            requirement_no="PR-1",
            status=RequirementStatus.PENDING_WAREHOUSE,
            version=7,
            building=RequirementBuilding(building_id=1, building_name="一号楼"),
            current_handler=RequirementHandler(employee_id=12, name="仓库管理员"),
            applicant_fields=ApplicantFields(device_name="交换机", quantity=quantity, unit="台"),
            purchase_fields=PurchaseFields(supplier_id=8, actual_total_price="25.00"),
            missing_fields=("warehouse_location", "received_quantity"),
            allowed_actions=(AllowedRequirementAction.UPDATE_WAREHOUSE_FIELDS,),
        )
    )
    return fake


@pytest.mark.asyncio
@pytest.mark.parametrize("received", ["2", "3"])
async def test_equal_and_over_receipt_complete_without_llm(received: str) -> None:
    fake = backend()
    service = WarehouseWorkflowService(fake)
    await service.save_warehouse_fields(
        identity(),
        1,
        7,
        WarehouseFieldsPatch(warehouse_location="A-01", received_quantity=received),
    )
    confirmation = await service.prepare_complete(identity(), 1)
    token = UUID(str(confirmation.actions[0].value["action_token"]))
    result = await service.confirm_complete(identity(), 1, 8, token)
    latest = await fake.get_requirement(identity=identity(), requirement_id=1)
    assert result.title == "入库已完成"
    assert latest.status is RequirementStatus.COMPLETED
    assert latest.current_handler is None
    assert latest.completed_at is not None
    assert fake.call_counts["append_agent_message"] == 0


@pytest.mark.asyncio
async def test_short_receipt_requires_remark_and_supports_partial_patch() -> None:
    fake = backend(quantity="5")
    service = WarehouseWorkflowService(fake)
    warning = await service.save_warehouse_fields(
        identity(),
        1,
        7,
        WarehouseFieldsPatch(warehouse_location="B-02", received_quantity="3"),
    )
    assert "入库备注必填" in warning.elements[0].markdown
    latest = await fake.get_requirement(identity=identity(), requirement_id=1)
    assert latest.missing_fields == ("receipt_remark",)
    await service.save_warehouse_fields(
        identity(), 1, 8, WarehouseFieldsPatch(receipt_remark="供应商少发 2 台")
    )
    latest = await fake.get_requirement(identity=identity(), requirement_id=1)
    assert latest.fields_complete is True
    assert latest.warehouse_fields is not None
    assert latest.warehouse_fields.warehouse_location == "B-02"


def test_received_quantity_must_be_positive_string_decimal() -> None:
    for value in ("0", "-1"):
        with pytest.raises(ValidationError):
            WarehouseFieldsPatch(received_quantity=value)
