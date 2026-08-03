from datetime import UTC, datetime
from uuid import UUID

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.purchaser.action_router import (
    _normalize_purchase_datetime,
)
from procurement_platform.application.purchaser.workflow_service import PurchaserWorkflowService
from procurement_platform.domain.enums import (
    AllowedRequirementAction,
    PlatformType,
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ApplicantFields,
    HandlerCandidate,
    HandlerCandidates,
    PurchaseFieldsPatch,
    RequirementBuilding,
    RequirementDetail,
    RequirementHandler,
    ReviewFields,
    SupplierDetail,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def identity() -> PlatformIdentity:
    return PlatformIdentity(PlatformType.TEST_PLATFORM, "ou_purchaser", "request")


def test_purchase_datetime_accepts_card_display_format() -> None:
    assert _normalize_purchase_datetime("2026-08-03 13:56") == "2026-08-03T13:56:00"
    assert _normalize_purchase_datetime("2026/08/03 13:56") == "2026-08-03T13:56:00"


def backend() -> FakeBackendClient:
    fake = FakeBackendClient(
        CurrentUser(
            employee_id=9,
            name="采购员",
            mobile=None,
            status="ACTIVE",
            roles=(UserRole(role_code=RoleCode.PURCHASER),),
            buildings=(UserBuilding(building_id=1, building_name="一号楼"),),
        )
    )
    fake.seed_requirement(
        RequirementDetail(
            requirement_id=1,
            requirement_no="PR-1",
            status=RequirementStatus.PENDING_PURCHASE,
            version=4,
            building=RequirementBuilding(building_id=1, building_name="一号楼"),
            current_handler=RequirementHandler(employee_id=9, name="采购员"),
            applicant_fields=ApplicantFields(device_name="交换机", quantity="2", unit="台"),
            review_fields=ReviewFields(
                proposed_supplier_id=8,
                proposed_supplier_name="示例供应商",
            ),
            missing_fields=(),
            allowed_actions=(AllowedRequirementAction.START_PURCHASE,),
        )
    )
    fake.seed_supplier(
        SupplierDetail(
            supplier_id=8,
            supplier_name="示例供应商",
            supplier_tax_number="TAX-8",
            bank_name="示例银行",
            bank_account="6222000012345678",
            bank_account_masked=False,
            registered_address="示例地址",
            contract_contact_info="contact@example.com",
        )
    )
    fake.handler_candidates = HandlerCandidates(
        items=(HandlerCandidate(employee_id=12, name="仓库管理员"),),
        auto_selected_employee_id=12,
    )
    return fake


@pytest.mark.asyncio
async def test_purchase_card_inherits_supplier_name_without_supplier_id_input() -> None:
    fake = backend()
    service = PurchaserWorkflowService(fake)
    await service.start_purchase(identity(), 1, 4, UUID("00000000-0000-0000-0000-000000000001"))
    view = await service.open_requirement(identity(), 1)
    serialized = str(view)
    assert "示例供应商" in serialized
    assert "supplier_id" not in serialized


@pytest.mark.asyncio
async def test_no_llm_purchaser_flow_reaches_pending_warehouse() -> None:
    fake = backend()
    service = PurchaserWorkflowService(fake)
    start_token = UUID("00000000-0000-0000-0000-000000000001")
    await service.start_purchase(identity(), 1, 4, start_token)
    await service.save_purchase_fields(
        identity(),
        1,
        5,
        PurchaseFieldsPatch(
            supplier_id=8,
            supplier_tax_number="TAX-8",
            bank_name="示例银行",
            bank_account="6222000012345678",
            registered_address="示例地址",
            contract_contact_info="contact@example.com",
            actual_unit_price="12.50",
            tax_rate="13",
            purchased_at=datetime(2026, 7, 30, tzinfo=UTC),
        ),
    )
    confirmation = await service.prepare_submit_warehouse(identity(), 1, None)
    token = confirmation.actions[0].value["action_token"]
    assert isinstance(token, str)
    result = await service.confirm_submit_warehouse(identity(), 1, 6, 12, UUID(token))
    latest = await fake.get_requirement(identity=identity(), requirement_id=1)
    assert result.title == "已提交仓库"
    assert latest.status is RequirementStatus.PENDING_WAREHOUSE
    assert latest.purchase_fields is not None
    assert latest.purchase_fields.actual_total_price == "25.00"
    assert latest.purchase_fields.update_supplier_profile is False
    assert fake.call_counts["append_agent_message"] == 0


@pytest.mark.asyncio
async def test_supplier_search_and_sensitive_repr() -> None:
    fake = backend()
    result = await fake.search_suppliers(identity=identity(), keyword="示例")
    detail = await fake.get_supplier(identity=identity(), supplier_id=8)
    assert result.total == 1
    assert "6222000012345678" not in repr(detail)
    with pytest.raises(ValueError):
        await fake.search_suppliers(identity=identity(), keyword="")
