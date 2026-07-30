from uuid import UUID, uuid4

from procurement_platform.application.building_manager.card_factory import (
    BuildingManagerCardFactory,
)
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
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import InteractionView
from procurement_platform.domain.requirement import (
    RequirementTransitionResult,
    ReviewFieldsPatch,
)
from procurement_platform.ports.backend_client import BackendClient


class BuildingManagerWorkflowService:
    def __init__(
        self, backend: BackendClient, cards: BuildingManagerCardFactory | None = None
    ) -> None:
        self._backend = backend
        self._cards = cards or BuildingManagerCardFactory()

    async def list_pending_requirements(
        self, identity: PlatformIdentity, page: int = 1
    ) -> InteractionView:
        result = await self._backend.list_requirements(
            identity=identity,
            view=RequirementView.PENDING_FOR_ME,
            status=RequirementStatus.PENDING_REVIEW,
            page=page,
        )
        return self._cards.listing(result)

    async def open_requirement(
        self, identity: PlatformIdentity, requirement_id: int
    ) -> InteractionView:
        return self._cards.detail(
            await self._backend.get_requirement(identity=identity, requirement_id=requirement_id)
        )

    async def save_review_fields(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: ReviewFieldsPatch,
    ) -> InteractionView:
        try:
            saved = await self._backend.update_review_fields(
                identity=identity,
                requirement_id=requirement_id,
                expected_version=expected_version,
                fields=fields,
            )
            detail = await self._backend.get_requirement(
                identity=identity, requirement_id=requirement_id
            )
            notice = (
                "审核字段已完整保存。"
                if saved.fields_complete
                else f"已保存, 仍缺少: {'、'.join(saved.missing_fields)}"
            )
            return self._cards.detail(detail, notice)
        except ConcurrentModificationError:
            detail = await self._backend.get_requirement(
                identity=identity, requirement_id=requirement_id
            )
            return self._cards.detail(detail, "版本冲突, 已加载后端最新字段, 请重新确认。")

    async def review_validation_error(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        message: str,
    ) -> InteractionView:
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        return self._cards.detail(detail, message)

    async def prepare_reject(
        self, identity: PlatformIdentity, requirement_id: int, reason: str | None
    ) -> InteractionView:
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        if not reason or not reason.strip():
            return self._cards.reject_form(detail)
        return self._cards.reject_confirmation(detail, reason.strip(), str(uuid4()))

    async def confirm_reject(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        reason: str,
        action_token: UUID,
    ) -> InteractionView:
        try:
            result = await self._backend.reject_requirement(
                identity=identity,
                requirement_id=requirement_id,
                expected_version=expected_version,
                reason=reason,
                action_token=action_token,
            )
            return self._cards.result(result, "已驳回")
        except (DuplicateOperationError, ConcurrentModificationError):
            return await self._transition_after_retry(
                identity, requirement_id, RequirementStatus.REJECTED, "已驳回"
            )

    async def prepare_submit_purchaser(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        employee_id: int | None,
    ) -> InteractionView:
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        if (
            detail.status is not RequirementStatus.PENDING_REVIEW
            or AllowedRequirementAction.SUBMIT_PURCHASER not in detail.allowed_actions
            or not detail.fields_complete
        ):
            return self._cards.detail(detail, "后端当前字段或状态不允许提交采购员。")
        candidates = await self._backend.list_handler_candidates(
            identity=identity,
            requirement_id=requirement_id,
            target_role=RoleCode.PURCHASER,
        )
        if not candidates.items:
            return self._cards.detail(detail, "当前没有可用采购员候选。")
        selected = next(
            (item for item in candidates.items if item.employee_id == employee_id), None
        )
        if selected is None and len(candidates.items) == 1:
            selected = candidates.items[0]
        if selected is None:
            return self._cards.purchaser_selection(detail, candidates)
        return self._cards.submit_confirmation(
            detail, selected.employee_id, selected.name, str(uuid4())
        )

    async def confirm_submit_purchaser(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        employee_id: int,
        action_token: UUID,
    ) -> InteractionView:
        latest = await self._backend.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        candidates = await self._backend.list_handler_candidates(
            identity=identity,
            requirement_id=requirement_id,
            target_role=RoleCode.PURCHASER,
        )
        selected = next(
            (item for item in candidates.items if item.employee_id == employee_id), None
        )
        if selected is None:
            return self._cards.purchaser_selection(latest, candidates)
        if latest.version != expected_version:
            return self._cards.detail(latest, "版本已变化, 请重新确认提交。")
        try:
            result = await self._backend.submit_purchaser(
                identity=identity,
                requirement_id=requirement_id,
                expected_version=latest.version,
                assigned_to_employee_id=employee_id,
                action_token=action_token,
            )
            return self._cards.result(result, "已提交采购员")
        except (DuplicateOperationError, ConcurrentModificationError, MissingRequiredFieldsError):
            return await self._transition_after_retry(
                identity, requirement_id, RequirementStatus.PENDING_PURCHASE, "已提交采购员"
            )

    async def _transition_after_retry(
        self,
        identity: PlatformIdentity,
        requirement_id: int,
        target: RequirementStatus,
        title: str,
    ) -> InteractionView:
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        if detail.status is target:
            return self._cards.result(
                RequirementTransitionResult(
                    requirement_id=detail.requirement_id,
                    requirement_no=detail.requirement_no,
                    status=detail.status,
                    version=detail.version,
                    current_handler=detail.current_handler,
                ),
                title,
            )
        return self._cards.detail(detail, "操作未完成, 已加载后端最新状态。")
