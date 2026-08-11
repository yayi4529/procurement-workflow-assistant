from uuid import UUID, uuid4

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.applicant.workflow_service import ApplicantWorkflowService
from procurement_platform.domain.enums import PlatformType, RequirementStatus, RoleCode
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import (
    KeyValueSection,
    MarkdownBlock,
    SelectInput,
    TextInput,
)
from procurement_platform.domain.requirement import (
    ApplicantFieldsPatch,
    HandlerCandidate,
    HandlerCandidates,
)
from procurement_platform.domain.user import CurrentUser, UserBuilding, UserRole


def identity() -> PlatformIdentity:
    return PlatformIdentity(PlatformType.TEST_PLATFORM, "ou_applicant", "request")


def backend(*, role: RoleCode = RoleCode.APPLICANT) -> FakeBackendClient:
    result = FakeBackendClient(
        CurrentUser(
            employee_id=1,
            name="申请人",
            mobile=None,
            status="ACTIVE",
            roles=(UserRole(role_code=role),),
            buildings=(
                UserBuilding(building_id=1, building_name="一号楼", is_primary=True),
                UserBuilding(building_id=2, building_name="二号楼"),
            ),
        )
    )
    result.handler_candidates = HandlerCandidates(
        items=(HandlerCandidate(employee_id=9, name="楼长"),),
        auto_selected_employee_id=9,
    )
    return result


@pytest.mark.asyncio
async def test_no_llm_applicant_flow_reaches_pending_review() -> None:
    fake = backend()
    service = ApplicantWorkflowService(fake)
    draft_view = await service.start_new(identity())
    assert draft_view.title == "采购申请详情"
    draft_summary = next(
        element for element in draft_view.elements if isinstance(element, KeyValueSection)
    )
    draft_fields = {field.label: field.value for field in draft_summary.fields}
    assert draft_fields["申请人"] == "申请人"
    assert len(draft_fields["申请时间"]) == 10
    assert "版本" not in draft_fields
    assert fake.call_counts["create_requirement"] == 1
    assert fake.call_counts["get_requirement"] == 1
    draft = await fake.create_requirement(identity=identity(), building_id=1)
    await service.save(
        identity(),
        draft.requirement_id,
        draft.version,
        ApplicantFieldsPatch(
            device_profession="服务器",
            device_name="硬盘",
            quantity="5",
            unit="块",
            application_reason="故障替换",
        ),
    )
    detail = await fake.get_requirement(identity=identity(), requirement_id=draft.requirement_id)
    assert detail.fields_complete is True
    assert detail.applicant_fields.brand is None
    assert detail.applicant_fields.model is None
    prepared = await service.prepare(identity(), draft.requirement_id, resubmit=False)
    assert prepared.title == "选择审批楼长"
    confirmation = await service.confirm_handler(
        identity(), draft.requirement_id, 9, resubmit=False
    )
    confirmation_summary = next(
        element for element in confirmation.elements if isinstance(element, KeyValueSection)
    )
    confirmation_fields = {field.label: field.value for field in confirmation_summary.fields}
    assert confirmation_fields["申请人"] == "申请人"
    assert len(confirmation_fields["申请时间"]) == 10
    button = confirmation.actions[0]
    token = button.value["action_token"]
    assert isinstance(token, str)
    result = await service.confirm(
        identity(),
        draft.requirement_id,
        detail.version,
        9,
        uuid4() if not token else UUID(token),
        resubmit=False,
    )
    latest = await fake.get_requirement(identity=identity(), requirement_id=draft.requirement_id)
    assert result.title == "提交成功"
    success_summary = next(
        element for element in result.elements if isinstance(element, KeyValueSection)
    )
    success_fields = {field.label: field.value for field in success_summary.fields}
    assert success_fields["采购单编号"].startswith("PR-")
    assert success_fields["设备名称"] == "硬盘"
    assert success_fields["申请人"] == "申请人"
    assert "版本" not in success_fields
    readonly_view = await service.open(identity(), draft.requirement_id)
    readonly_summary = next(
        element for element in readonly_view.elements if isinstance(element, KeyValueSection)
    )
    readonly_fields = {field.label: field.value for field in readonly_summary.fields}
    assert readonly_fields["设备专业"] == "服务器"
    assert readonly_fields["设备名称"] == "硬盘"
    assert readonly_fields["数量和单位"] == "5 块"
    assert readonly_fields["需求原因"] == "故障替换"
    assert "版本" not in readonly_fields
    assert latest.status is RequirementStatus.PENDING_REVIEW
    assert fake.call_counts["submit_review"] == 1
    assert fake.call_counts["resubmit_review"] == 0


@pytest.mark.asyncio
async def test_patch_distinguishes_unset_and_explicit_null() -> None:
    fake = backend()
    summary = await fake.create_requirement(identity=identity(), building_id=1)
    first = await fake.update_applicant_fields(
        identity=identity(),
        requirement_id=summary.requirement_id,
        expected_version=summary.version,
        fields=ApplicantFieldsPatch(device_name="硬盘", brand="希捷", quantity="2"),
    )
    await fake.update_applicant_fields(
        identity=identity(),
        requirement_id=summary.requirement_id,
        expected_version=first.version,
        fields=ApplicantFieldsPatch(brand=None),
    )
    detail = await fake.get_requirement(identity=identity(), requirement_id=summary.requirement_id)
    assert detail.applicant_fields.device_name == "硬盘"
    assert detail.applicant_fields.quantity == "2"
    assert detail.applicant_fields.brand is None


@pytest.mark.asyncio
async def test_non_applicant_cannot_create_and_form_marks_brand_model_optional() -> None:
    fake = backend(role=RoleCode.PURCHASER)
    service = ApplicantWorkflowService(fake)
    view = await service.start_new(identity())
    assert view.title == "无权限"
    assert fake.call_counts["create_requirement"] == 0

    applicant = backend()
    summary = await applicant.create_requirement(identity=identity(), building_id=1)
    detail_view = await ApplicantWorkflowService(applicant).open(identity(), summary.requirement_id)
    inputs = {
        element.name: element for element in detail_view.elements if isinstance(element, TextInput)
    }
    assert inputs["brand"].required is False
    assert inputs["model"].required is False
    professions = [
        element
        for element in detail_view.elements
        if isinstance(element, SelectInput) and element.name == "device_profession"
    ]
    assert len(professions) == 1
    assert professions[0].required is True
    assert all(
        "当前缺少" not in element.markdown
        for element in detail_view.elements
        if isinstance(element, MarkdownBlock)
    )
    action_ids = {action.action_id for action in detail_view.actions}
    assert "applicant.save" not in action_ids
    prepare = next(
        action for action in detail_view.actions if action.action_id == "applicant.prepare_submit"
    )
    assert prepare.value["expected_version"] == summary.version


@pytest.mark.asyncio
async def test_prepare_saves_form_fields_before_selecting_handler() -> None:
    fake = backend()
    summary = await fake.create_requirement(identity=identity(), building_id=1)
    service = ApplicantWorkflowService(fake)

    prepared = await service.prepare(
        identity(),
        summary.requirement_id,
        expected_version=summary.version,
        fields=ApplicantFieldsPatch(
            device_profession="弱电",
            device_name="交换机",
            quantity="1",
            unit="台",
            application_reason="网络扩容",
        ),
        resubmit=False,
    )

    detail = await fake.get_requirement(identity=identity(), requirement_id=summary.requirement_id)
    assert prepared.title == "选择审批楼长"
    assert detail.fields_complete is True
    assert fake.call_counts["update_applicant_fields"] == 1
    assert fake.call_counts["list_handler_candidates"] == 1


@pytest.mark.asyncio
async def test_rejected_requirement_uses_resubmit_and_keeps_identity() -> None:
    fake = backend()
    summary = await fake.create_requirement(identity=identity(), building_id=1)
    saved = await fake.update_applicant_fields(
        identity=identity(),
        requirement_id=summary.requirement_id,
        expected_version=summary.version,
        fields=ApplicantFieldsPatch(
            device_profession="网络",
            device_name="交换机",
            quantity="1",
            unit="台",
            application_reason="扩容",
        ),
    )
    original = await fake.get_requirement(
        identity=identity(), requirement_id=summary.requirement_id
    )
    fake.seed_requirement(
        original.model_copy(
            update={"status": RequirementStatus.REJECTED, "rejection_reason": "请补充说明"}
        )
    )
    service = ApplicantWorkflowService(fake)
    result = await service.confirm(
        identity(),
        summary.requirement_id,
        saved.version,
        9,
        uuid4(),
        resubmit=True,
    )
    latest = await fake.get_requirement(identity=identity(), requirement_id=summary.requirement_id)
    assert result.title == "提交成功"
    assert latest.requirement_id == original.requirement_id
    assert latest.requirement_no == original.requirement_no
    assert fake.call_counts["resubmit_review"] == 1
    assert fake.call_counts["submit_review"] == 0
