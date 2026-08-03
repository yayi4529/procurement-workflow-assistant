from datetime import date
from uuid import UUID

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.building_manager.action_router import (
    _normalize_feishu_date,
)
from procurement_platform.application.building_manager.workflow_service import (
    BuildingManagerWorkflowService,
)
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
    RequirementBuilding,
    RequirementDetail,
    RequirementHandler,
    ReviewFieldsPatch,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def identity() -> PlatformIdentity:
    return PlatformIdentity(PlatformType.TEST_PLATFORM, "ou_manager", "request")


def test_feishu_date_value_discards_timezone_suffix() -> None:
    assert _normalize_feishu_date("2026-08-02 +0800") == "2026-08-02"
    assert _normalize_feishu_date("2026-08-02") == "2026-08-02"


def test_review_card_marks_backend_required_warranty_as_required() -> None:
    from procurement_platform.application.building_manager.card_factory import (
        BuildingManagerCardFactory,
    )
    from procurement_platform.domain.interaction import TextInput

    detail = backend()._requirements[1]
    view = BuildingManagerCardFactory().detail(detail)
    warranty = next(
        element
        for element in view.elements
        if isinstance(element, TextInput) and element.name == "warranty_info"
    )
    assert warranty.required is True


def backend() -> FakeBackendClient:
    fake = FakeBackendClient(
        CurrentUser(
            employee_id=7,
            name="楼长",
            mobile=None,
            status="ACTIVE",
            roles=(UserRole(role_code=RoleCode.BUILDING_MANAGER),),
            buildings=(UserBuilding(building_id=1, building_name="一号楼"),),
        )
    )
    fake.seed_requirement(
        RequirementDetail(
            requirement_id=1,
            requirement_no="PR-1",
            status=RequirementStatus.PENDING_REVIEW,
            version=2,
            building=RequirementBuilding(building_id=1, building_name="一号楼"),
            current_handler=RequirementHandler(employee_id=7, name="楼长"),
            applicant_fields=ApplicantFields(
                device_profession="网络",
                device_name="交换机",
                quantity="2",
                unit="台",
                application_reason="扩容",
            ),
            missing_fields=(),
            allowed_actions=(
                AllowedRequirementAction.UPDATE_REVIEW_FIELDS,
                AllowedRequirementAction.REJECT,
            ),
        )
    )
    fake.handler_candidates = HandlerCandidates(
        items=(HandlerCandidate(employee_id=9, name="采购员"),),
        auto_selected_employee_id=9,
    )
    return fake


async def save_complete(fake: FakeBackendClient) -> int:
    result = await fake.update_review_fields(
        identity=identity(),
        requirement_id=1,
        expected_version=2,
        fields=ReviewFieldsPatch(
            proposed_supplier_name="测试供应商",
            supplier_contact_name="王工",
            supplier_contact_info="13800000000",
            estimated_unit_price="12.50",
            need_contract=True,
            contract_type="采购合同",
            payment_method="对公转账",
            expected_arrival_date=date(2026, 8, 1),
        ),
    )
    assert result.review_fields.estimated_total_price == "25.00"
    assert result.fields_complete is True
    return result.version


@pytest.mark.asyncio
async def test_no_llm_manager_save_and_submit_reaches_pending_purchase() -> None:
    fake = backend()
    version = await save_complete(fake)
    service = BuildingManagerWorkflowService(fake)
    confirmation = await service.prepare_submit_purchaser(identity(), 1, None)
    assert confirmation.title == "确认提交采购员"
    token = confirmation.actions[0].value["action_token"]
    assert isinstance(token, str)
    result = await service.confirm_submit_purchaser(identity(), 1, version, 9, UUID(token))
    latest = await fake.get_requirement(identity=identity(), requirement_id=1)
    assert result.title == "已提交采购员"
    assert latest.status is RequirementStatus.PENDING_PURCHASE
    assert fake.call_counts["submit_purchaser"] == 1
    assert fake.call_counts["append_agent_message"] == 0


@pytest.mark.asyncio
async def test_no_llm_manager_reject_requires_confirmation_and_is_idempotent() -> None:
    fake = backend()
    service = BuildingManagerWorkflowService(fake)
    form = await service.prepare_reject(identity(), 1, "")
    assert form.title == "驳回采购申请"
    confirmation = await service.prepare_reject(identity(), 1, "信息不足")
    token = confirmation.actions[0].value["action_token"]
    assert isinstance(token, str)
    first = await service.confirm_reject(identity(), 1, 2, "信息不足", UUID(token))
    second = await service.confirm_reject(identity(), 1, 2, "信息不足", UUID(token))
    assert first.title == second.title == "已驳回"
    assert (
        await fake.get_requirement(identity=identity(), requirement_id=1)
    ).status is RequirementStatus.REJECTED
    assert fake.call_counts["reject_requirement"] == 2


@pytest.mark.asyncio
async def test_contract_type_is_conditionally_required_and_null_is_explicit() -> None:
    fake = backend()
    saved = await fake.update_review_fields(
        identity=identity(),
        requirement_id=1,
        expected_version=2,
        fields=ReviewFieldsPatch(need_contract=True, contract_type=None),
    )
    assert "contract_type" in saved.missing_fields
    detail = await fake.get_requirement(identity=identity(), requirement_id=1)
    assert detail.review_fields is not None
    assert detail.review_fields.contract_type is None
