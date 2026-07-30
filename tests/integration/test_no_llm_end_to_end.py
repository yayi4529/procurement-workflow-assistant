from dataclasses import fields
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.applicant.workflow_service import (
    ApplicantWorkflowService,
)
from procurement_platform.application.building_manager.workflow_service import (
    BuildingManagerWorkflowService,
)
from procurement_platform.application.purchaser.workflow_service import (
    PurchaserWorkflowService,
)
from procurement_platform.application.warehouse.workflow_service import (
    WarehouseWorkflowService,
)
from procurement_platform.bootstrap.container import ApplicationContainer
from procurement_platform.bootstrap.settings import Settings
from procurement_platform.domain.enums import PlatformType, RequirementStatus, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ApplicantFieldsPatch,
    HandlerCandidate,
    HandlerCandidates,
    PurchaseFieldsPatch,
    ReviewFieldsPatch,
    WarehouseFieldsPatch,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def user(employee_id: int, name: str, role: RoleCode) -> CurrentUser:
    return CurrentUser(
        employee_id=employee_id,
        name=name,
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=role),),
        buildings=(UserBuilding(building_id=1, building_name="一号楼", is_primary=True),),
    )


def identity(open_id: str) -> PlatformIdentity:
    return PlatformIdentity(PlatformType.TEST_PLATFORM, open_id, f"trace-{open_id}")


def candidate(employee_id: int, name: str) -> HandlerCandidates:
    return HandlerCandidates(
        items=(HandlerCandidate(employee_id=employee_id, name=name),),
        auto_selected_employee_id=employee_id,
    )


async def detail(fake: FakeBackendClient, requirement_id: int):
    return await fake.get_requirement(
        identity=identity("inspection"), requirement_id=requirement_id
    )


@pytest.mark.asyncio
async def test_formal_container_builds_with_llm_disabled_and_no_openai_configuration() -> None:
    settings = Settings.from_env(
        {
            "PROCUREMENT_ENVIRONMENT": "test",
            "PROCUREMENT_SERVICE_NAME": "no-llm-e2e",
            "PROCUREMENT_BACKEND_BASE_URL": "http://backend.invalid",
            "PROCUREMENT_BACKEND_REQUEST_TIMEOUT_SECONDS": "1",
            "PROCUREMENT_IDENTITY_GATEWAY_SECRET": "test-secret",
            "PROCUREMENT_LLM_ENABLED": "false",
        }
    )
    container = ApplicationContainer.build(settings)
    try:
        assert settings.llm_enabled is False
        assert not any(
            "llm" in item.name.lower() or "assistant" in item.name.lower()
            for item in fields(container)
        )
    finally:
        await container.aclose()


@pytest.mark.asyncio
async def test_reject_resubmit_then_full_four_role_flow_without_agent_session() -> None:
    applicant = user(1, "需求人", RoleCode.APPLICANT)
    manager = user(7, "楼长", RoleCode.BUILDING_MANAGER)
    purchaser = user(9, "采购员", RoleCode.PURCHASER)
    warehouse = user(12, "仓库管理员", RoleCode.WAREHOUSE_MANAGER)
    fake = FakeBackendClient(applicant)
    applicant_service = ApplicantWorkflowService(fake)
    manager_service = BuildingManagerWorkflowService(fake)
    purchaser_service = PurchaserWorkflowService(fake)
    warehouse_service = WarehouseWorkflowService(fake)
    statuses: list[RequirementStatus] = []

    await applicant_service.create_draft(identity("applicant"), 1)
    requirement_id = 1
    current = await detail(fake, requirement_id)
    statuses.append(current.status)
    await applicant_service.save(
        identity("applicant"),
        requirement_id,
        current.version,
        ApplicantFieldsPatch(
            device_profession="网络",
            device_name="交换机",
            quantity="2",
            unit="台",
            application_reason="扩容",
        ),
    )
    fake.handler_candidates = candidate(7, "楼长")
    current = await detail(fake, requirement_id)
    await applicant_service.confirm(
        identity("applicant"),
        requirement_id,
        current.version,
        7,
        UUID("00000000-0000-0000-0000-000000000001"),
        resubmit=False,
    )
    statuses.append((await detail(fake, requirement_id)).status)

    fake.current_user = manager
    current = await detail(fake, requirement_id)
    await manager_service.confirm_reject(
        identity("manager"),
        requirement_id,
        current.version,
        "请补充业务说明",
        UUID("00000000-0000-0000-0000-000000000002"),
    )
    statuses.append((await detail(fake, requirement_id)).status)

    fake.current_user = applicant
    current = await detail(fake, requirement_id)
    await applicant_service.save(
        identity("applicant"),
        requirement_id,
        current.version,
        ApplicantFieldsPatch(application_reason="核心网络扩容"),
    )
    fake.handler_candidates = candidate(7, "楼长")
    current = await detail(fake, requirement_id)
    await applicant_service.confirm(
        identity("applicant"),
        requirement_id,
        current.version,
        7,
        UUID("00000000-0000-0000-0000-000000000003"),
        resubmit=True,
    )
    statuses.append((await detail(fake, requirement_id)).status)

    fake.current_user = manager
    current = await detail(fake, requirement_id)
    await manager_service.save_review_fields(
        identity("manager"),
        requirement_id,
        current.version,
        ReviewFieldsPatch(
            proposed_supplier_id=8,
            supplier_contact_name="王工",
            supplier_contact_info="13800000000",
            estimated_unit_price="100.00",
            need_contract=False,
            payment_method="对公转账",
            expected_arrival_date=date(2026, 8, 15),
        ),
    )
    fake.handler_candidates = candidate(9, "采购员")
    current = await detail(fake, requirement_id)
    await manager_service.confirm_submit_purchaser(
        identity("manager"),
        requirement_id,
        current.version,
        9,
        UUID("00000000-0000-0000-0000-000000000004"),
    )
    statuses.append((await detail(fake, requirement_id)).status)

    fake.current_user = purchaser
    current = await detail(fake, requirement_id)
    await purchaser_service.start_purchase(
        identity("purchaser"),
        requirement_id,
        current.version,
        UUID("00000000-0000-0000-0000-000000000005"),
    )
    statuses.append((await detail(fake, requirement_id)).status)
    current = await detail(fake, requirement_id)
    await purchaser_service.save_purchase_fields(
        identity("purchaser"),
        requirement_id,
        current.version,
        PurchaseFieldsPatch(
            supplier_id=8,
            supplier_tax_number="TAX-8",
            bank_name="示例银行",
            bank_account="6222000012345678",
            registered_address="示例地址",
            contract_contact_info="contact@example.com",
            actual_unit_price="90.00",
            tax_rate="13",
            purchased_at=datetime(2026, 7, 30, tzinfo=UTC),
        ),
    )
    fake.handler_candidates = candidate(12, "仓库管理员")
    current = await detail(fake, requirement_id)
    await purchaser_service.confirm_submit_warehouse(
        identity("purchaser"),
        requirement_id,
        current.version,
        12,
        UUID("00000000-0000-0000-0000-000000000006"),
    )
    statuses.append((await detail(fake, requirement_id)).status)

    fake.current_user = warehouse
    current = await detail(fake, requirement_id)
    await warehouse_service.save_warehouse_fields(
        identity("warehouse"),
        requirement_id,
        current.version,
        WarehouseFieldsPatch(warehouse_location="A-01", received_quantity="2"),
    )
    current = await detail(fake, requirement_id)
    await warehouse_service.confirm_complete(
        identity("warehouse"),
        requirement_id,
        current.version,
        UUID("00000000-0000-0000-0000-000000000007"),
    )
    statuses.append((await detail(fake, requirement_id)).status)

    assert statuses == [
        RequirementStatus.DRAFT,
        RequirementStatus.PENDING_REVIEW,
        RequirementStatus.REJECTED,
        RequirementStatus.PENDING_REVIEW,
        RequirementStatus.PENDING_PURCHASE,
        RequirementStatus.PURCHASING,
        RequirementStatus.PENDING_WAREHOUSE,
        RequirementStatus.COMPLETED,
    ]
    agent_methods = {
        "get_or_create_agent_conversation",
        "append_agent_message",
        "list_agent_messages",
        "get_agent_state",
        "update_agent_state",
        "snapshot_agent_state",
        "complete_agent_conversation",
    }
    assert agent_methods.isdisjoint(call.method for call in fake.calls)
