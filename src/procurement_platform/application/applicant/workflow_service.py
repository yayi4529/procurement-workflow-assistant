from datetime import UTC, datetime
from uuid import UUID, uuid4

from procurement_platform.application.applicant.card_factory import ApplicantCardFactory
from procurement_platform.domain.enums import (
    AllowedRequirementAction,
    RequirementStatus,
    RequirementView,
    RoleCode,
)
from procurement_platform.domain.errors import (
    ConcurrentModificationError,
    DuplicateOperationError,
    MissingRequiredFieldsError,
    ValidationError,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import InteractionView
from procurement_platform.domain.requirement import ApplicantFieldsPatch, RequirementDetail
from procurement_platform.ports.backend_client import BackendClient


class ApplicantWorkflowService:
    def __init__(self, backend: BackendClient, cards: ApplicantCardFactory | None = None) -> None:
        self._backend = backend
        self._cards = cards or ApplicantCardFactory()

    async def _detail(self, identity: PlatformIdentity, requirement_id: int) -> RequirementDetail:
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        user = await self._backend.get_current_user(identity=identity)
        records = await self._backend.list_purchase_records(
            identity=identity,
            requirement_no=detail.requirement_no,
            page=1,
            page_size=20,
        )
        record = next(
            (item for item in records.items if item.requirement_id == detail.requirement_id), None
        )
        return detail.model_copy(
            update={
                "applicant_name": user.name,
                "created_at": record.created_at if record is not None else datetime.now(UTC),
            }
        )

    async def home(self) -> InteractionView:
        return self._cards.home()

    async def start_new(self, identity: PlatformIdentity) -> InteractionView:
        user = await self._backend.get_current_user(identity=identity)
        if user.status != "ACTIVE":
            return self._cards.message("无法创建", "当前账号未启用。")
        if not any(role.role_code is RoleCode.APPLICANT for role in user.roles):
            return self._cards.message("无权限", "当前账号没有需求人角色。")
        if not user.buildings:
            return self._cards.message("无法创建", "当前账号没有可用楼宇, 请联系管理员。")
        primary = [item for item in user.buildings if item.is_primary]
        building = (
            user.buildings[0]
            if len(user.buildings) == 1
            else primary[0]
            if len(primary) == 1
            else None
        )
        if building is None:
            return self._cards.message(
                "无法创建",
                "当前账号有多个可用楼宇, 但后端未返回唯一主楼宇, 请联系管理员。",
            )
        summary = await self._backend.create_requirement(
            identity=identity, building_id=building.building_id
        )
        detail = await self._detail(identity, summary.requirement_id)
        return self._cards.detail(detail)

    async def create_draft(self, identity: PlatformIdentity, building_id: int) -> InteractionView:
        user = await self._backend.get_current_user(identity=identity)
        if user.status != "ACTIVE" or not any(
            role.role_code is RoleCode.APPLICANT for role in user.roles
        ):
            return self._cards.message("无权限", "当前账号不能创建采购申请。")
        if building_id not in {item.building_id for item in user.buildings}:
            return self._cards.message("楼宇不可用", "请选择后端返回的有效楼宇。")
        summary = await self._backend.create_requirement(identity=identity, building_id=building_id)
        detail = await self._detail(identity, summary.requirement_id)
        return self._cards.detail(detail)

    async def open(self, identity: PlatformIdentity, requirement_id: int) -> InteractionView:
        return self._cards.detail(await self._detail(identity, requirement_id))

    async def save(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: ApplicantFieldsPatch,
    ) -> InteractionView:
        try:
            saved = await self._backend.update_applicant_fields(
                identity=identity,
                requirement_id=requirement_id,
                expected_version=expected_version,
                fields=fields,
            )
            detail = await self._detail(identity, requirement_id)
            notice = (
                "保存成功, 字段已完整。"
                if saved.fields_complete
                else f"保存成功, 下一缺失字段: {saved.next_missing_field}"
            )
            return self._cards.detail(detail, notice=notice)
        except ConcurrentModificationError:
            detail = await self._detail(identity, requirement_id)
            return self._cards.detail(
                detail, notice="版本冲突: 已加载后端最新内容, 请重新确认修改。"
            )

    async def prepare(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        *,
        resubmit: bool,
        expected_version: int | None = None,
        fields: ApplicantFieldsPatch | None = None,
    ) -> InteractionView:
        if expected_version is not None and fields is not None and fields.provided_fields():
            try:
                await self._backend.update_applicant_fields(
                    identity=identity,
                    requirement_id=requirement_id,
                    expected_version=expected_version,
                    fields=fields,
                )
            except ConcurrentModificationError:
                detail = await self._detail(identity, requirement_id)
                return self._cards.detail(
                    detail,
                    notice="版本已变化，我已刷新后端最新内容，请重新检查后再提交。",  # noqa: RUF001
                )
            except ValidationError:
                detail = await self._detail(identity, requirement_id)
                return self._cards.detail(
                    detail,
                    notice=(
                        "保存失败：后端校验未通过。请确认设备专业使用下拉选项，"  # noqa: RUF001
                        "数量为大于 0 的数字。"
                    ),
                )
        detail = await self._detail(identity, requirement_id)
        action = (
            AllowedRequirementAction.RESUBMIT_REVIEW
            if resubmit
            else AllowedRequirementAction.SUBMIT_REVIEW
        )
        expected_status = RequirementStatus.REJECTED if resubmit else RequirementStatus.DRAFT
        if detail.status is not expected_status or action not in detail.allowed_actions:
            return self._cards.detail(detail, notice="后端当前状态不允许此操作。")
        if not detail.fields_complete or detail.missing_fields:
            return self._cards.detail(detail, notice="请先补全后端列出的必填字段。")
        candidates = await self._backend.list_handler_candidates(
            identity=identity,
            requirement_id=requirement_id,
            target_role=RoleCode.BUILDING_MANAGER,
        )
        if not candidates.items:
            return self._cards.detail(detail, notice="当前没有可用楼长候选人。")
        return self._cards.handler_selection(detail, candidates, resubmit=resubmit)

    async def confirm_handler(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        employee_id: int,
        *,
        resubmit: bool,
    ) -> InteractionView:
        detail = await self._detail(identity, requirement_id)
        candidates = await self._backend.list_handler_candidates(
            identity=identity,
            requirement_id=requirement_id,
            target_role=RoleCode.BUILDING_MANAGER,
        )
        selected = next(
            (item for item in candidates.items if item.employee_id == employee_id), None
        )
        if selected is None:
            return self._cards.handler_selection(detail, candidates, resubmit=resubmit)
        return self._cards.confirmation(
            detail, selected.employee_id, selected.name, str(uuid4()), resubmit=resubmit
        )

    async def confirm(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        employee_id: int,
        action_token: UUID,
        *,
        resubmit: bool,
    ) -> InteractionView:
        candidates = await self._backend.list_handler_candidates(
            identity=identity,
            requirement_id=requirement_id,
            target_role=RoleCode.BUILDING_MANAGER,
        )
        if employee_id not in {item.employee_id for item in candidates.items}:
            detail = await self._detail(identity, requirement_id)
            return self._cards.handler_selection(detail, candidates, resubmit=resubmit)
        operation = self._backend.resubmit_review if resubmit else self._backend.submit_review
        try:
            result = await operation(
                identity=identity,
                requirement_id=requirement_id,
                expected_version=expected_version,
                assigned_to_employee_id=employee_id,
                action_token=action_token,
            )
            detail = await self._detail(identity, result.requirement_id)
            return self._cards.success(detail)
        except (DuplicateOperationError, ConcurrentModificationError, MissingRequiredFieldsError):
            detail = await self._detail(identity, requirement_id)
            if detail.status is RequirementStatus.PENDING_REVIEW:
                return self._cards.success(detail)
            return self._cards.detail(detail, notice="操作未完成, 已加载后端最新状态。")

    async def listing(self, identity: PlatformIdentity, page: int = 1) -> InteractionView:
        result = await self._backend.list_requirements(
            identity=identity, view=RequirementView.CREATED_BY_ME, page=page
        )
        return self._cards.listing(result)
