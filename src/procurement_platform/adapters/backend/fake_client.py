from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from procurement_platform.domain.assistant_session import (
    AgentConversation,
    AgentConversationCompletion,
    AgentMessage,
    AgentMessagePage,
    AgentMessageWriteResult,
    AgentSessionSnapshot,
    AgentSessionState,
    AgentSessionStateUpdate,
    AgentStateSaveResult,
)
from procurement_platform.domain.enums import (
    AgentConversationStatus,
    AgentMessageSender,
    AllowedRequirementAction,
    RequirementStatus,
    RequirementView,
    ReviewStatus,
    RoleCode,
)
from procurement_platform.domain.errors import (
    BackendApplicationError,
    ConcurrentModificationError,
    DuplicateOperationError,
    InvalidHandlerError,
    InvalidStatusError,
    MissingRequiredFieldsError,
    PermissionDeniedError,
    SessionNotFoundError,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ApplicantFields,
    ApplicantFieldsPatch,
    ApplicantFieldsSaveResult,
    HandlerCandidates,
    RequirementBuilding,
    RequirementDetail,
    RequirementHandler,
    RequirementListItem,
    RequirementPage,
    RequirementSummary,
    RequirementTransitionResult,
    ReviewFields,
    ReviewFieldsPatch,
    ReviewFieldsSaveResult,
    ReviewRecordSummary,
)
from procurement_platform.domain.user import CurrentUser


@dataclass(frozen=True, slots=True)
class FakeCall:
    method: str
    conversation_id: int | None = None


class FakeBackendClient:
    def __init__(self, current_user: CurrentUser) -> None:
        self.current_user = current_user
        self.calls: list[FakeCall] = []
        self.call_counts: Counter[str] = Counter()
        self._failures: dict[str, BackendApplicationError] = {}
        self._conversations: dict[int, AgentConversation] = {}
        self._messages: dict[int, list[AgentMessage]] = {}
        self._external_ids: dict[tuple[int, str], AgentMessageWriteResult] = {}
        self._states: dict[int, AgentSessionState] = {}
        self.snapshots: list[AgentSessionSnapshot] = []
        self._next_conversation_id = 1
        self._next_message_id = 1
        self._requirements: dict[int, RequirementDetail] = {}
        self.handler_candidates = HandlerCandidates(items=())
        self._action_results: dict[UUID, RequirementTransitionResult] = {}
        self._next_requirement_id = 1

    def inject_error(self, method: str, error: BackendApplicationError) -> None:
        self._failures[method] = error

    def _record(self, method: str, conversation_id: int | None = None) -> None:
        self.calls.append(FakeCall(method, conversation_id))
        self.call_counts[method] += 1
        error = self._failures.get(method)
        if error is not None:
            raise error

    async def get_current_user(self, *, identity: PlatformIdentity) -> CurrentUser:
        self._record("get_current_user")
        return self.current_user

    def seed_requirement(self, detail: RequirementDetail) -> None:
        self._requirements[detail.requirement_id] = detail
        self._next_requirement_id = max(self._next_requirement_id, detail.requirement_id + 1)

    async def create_requirement(
        self, *, identity: PlatformIdentity, building_id: int
    ) -> RequirementSummary:
        self._record("create_requirement")
        building = next(
            (item for item in self.current_user.buildings if item.building_id == building_id),
            None,
        )
        if building is None:
            from procurement_platform.domain.errors import PermissionDeniedError

            raise PermissionDeniedError("BUILDING_NOT_ALLOWED", "无权使用该楼宇")
        requirement_id = self._next_requirement_id
        self._next_requirement_id += 1
        detail = RequirementDetail(
            requirement_id=requirement_id,
            requirement_no=f"PR-{requirement_id:06d}",
            status=RequirementStatus.DRAFT,
            version=1,
            building=RequirementBuilding(
                building_id=building.building_id, building_name=building.building_name
            ),
            applicant_fields=ApplicantFields(),
            missing_fields=(
                "device_profession",
                "device_name",
                "quantity",
                "unit",
                "application_reason",
            ),
            allowed_actions=(AllowedRequirementAction.UPDATE_APPLICANT_FIELDS,),
        )
        self._requirements[requirement_id] = detail
        return RequirementSummary.model_validate(
            detail.model_dump(include={"requirement_id", "requirement_no", "status", "version"})
        )

    def _require_requirement(self, requirement_id: int) -> RequirementDetail:
        try:
            return self._requirements[requirement_id]
        except KeyError as exc:
            from procurement_platform.domain.errors import RequirementNotFoundError

            raise RequirementNotFoundError("REQUIREMENT_NOT_FOUND", "采购申请不存在") from exc

    async def update_applicant_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: ApplicantFieldsPatch,
    ) -> ApplicantFieldsSaveResult:
        self._record("update_applicant_fields")
        detail = self._require_requirement(requirement_id)
        if detail.status not in {RequirementStatus.DRAFT, RequirementStatus.REJECTED}:
            raise InvalidStatusError("INVALID_STATUS", "当前状态不可修改")
        if detail.version != expected_version:
            raise ConcurrentModificationError("CONCURRENT_MODIFICATION", "版本冲突")
        merged = detail.applicant_fields.model_copy(update=fields.provided_fields())
        required = (
            "device_profession",
            "device_name",
            "quantity",
            "unit",
            "application_reason",
        )
        missing = tuple(name for name in required if not getattr(merged, name))
        actions = [AllowedRequirementAction.UPDATE_APPLICANT_FIELDS]
        if not missing:
            actions.append(
                AllowedRequirementAction.RESUBMIT_REVIEW
                if detail.status is RequirementStatus.REJECTED
                else AllowedRequirementAction.SUBMIT_REVIEW
            )
        updated = detail.model_copy(
            update={
                "applicant_fields": merged,
                "version": detail.version + 1,
                "missing_fields": missing,
                "fields_complete": not missing,
                "allowed_actions": tuple(actions),
            }
        )
        self._requirements[requirement_id] = updated
        return ApplicantFieldsSaveResult(
            requirement_id=requirement_id,
            status=updated.status,
            version=updated.version,
            missing_fields=missing,
            next_missing_field=missing[0] if missing else None,
            fields_complete=not missing,
        )

    async def get_requirement(
        self, *, identity: PlatformIdentity, requirement_id: int
    ) -> RequirementDetail:
        self._record("get_requirement")
        return self._require_requirement(requirement_id)

    async def list_requirements(
        self,
        *,
        identity: PlatformIdentity,
        view: RequirementView,
        status: RequirementStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> RequirementPage:
        self._record("list_requirements")
        if view not in {
            RequirementView.CREATED_BY_ME,
            RequirementView.PENDING_FOR_ME,
            RequirementView.PROCESSED_BY_ME,
        }:
            raise ValueError("unsupported view")
        values = [
            item
            for item in self._requirements.values()
            if (status is None or item.status is status)
            and (
                view is RequirementView.CREATED_BY_ME
                or (
                    view is RequirementView.PENDING_FOR_ME
                    and item.current_handler is not None
                    and item.current_handler.employee_id == self.current_user.employee_id
                )
                or (
                    view is RequirementView.PROCESSED_BY_ME
                    and item.current_handler is None
                    and item.review_record is not None
                )
            )
        ]
        start = (page - 1) * page_size
        items = tuple(
            RequirementListItem(
                requirement_id=item.requirement_id,
                requirement_no=item.requirement_no,
                status=item.status,
                version=item.version,
                device_name=item.applicant_fields.device_name,
                current_handler=item.current_handler,
            )
            for item in values[start : start + page_size]
        )
        return RequirementPage(items=items, page=page, page_size=page_size, total=len(values))

    async def list_handler_candidates(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        target_role: RoleCode,
    ) -> HandlerCandidates:
        self._record("list_handler_candidates")
        self._require_requirement(requirement_id)
        if target_role not in {RoleCode.BUILDING_MANAGER, RoleCode.PURCHASER}:
            raise ValueError("unsupported target role")
        return self.handler_candidates

    async def _transition(
        self,
        expected_status: RequirementStatus,
        *,
        method: str,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        self._record(method)
        duplicate = self._action_results.get(action_token)
        if duplicate is not None:
            raise DuplicateOperationError("DUPLICATE_OPERATION", "操作已执行")
        detail = self._require_requirement(requirement_id)
        if detail.status is not expected_status:
            raise InvalidStatusError("INVALID_STATUS", "当前状态不可提交")
        if detail.version != expected_version:
            raise ConcurrentModificationError("CONCURRENT_MODIFICATION", "版本冲突")
        if not detail.fields_complete:
            raise MissingRequiredFieldsError("MISSING_REQUIRED_FIELDS", "必填字段不完整")
        candidate = next(
            (
                item
                for item in self.handler_candidates.items
                if item.employee_id == assigned_to_employee_id
            ),
            None,
        )
        if candidate is None:
            raise InvalidHandlerError("INVALID_HANDLER", "处理人不在候选列表")
        handler = RequirementHandler(employee_id=candidate.employee_id, name=candidate.name)
        updated = detail.model_copy(
            update={
                "status": RequirementStatus.PENDING_REVIEW,
                "version": detail.version + 1,
                "current_handler": handler,
                "allowed_actions": (),
            }
        )
        self._requirements[requirement_id] = updated
        result = RequirementTransitionResult(
            requirement_id=updated.requirement_id,
            requirement_no=updated.requirement_no,
            status=updated.status,
            version=updated.version,
            current_handler=updated.current_handler,
            action_token=action_token,
        )
        self._action_results[action_token] = result
        return result

    async def submit_review(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        return await self._transition(
            RequirementStatus.DRAFT,
            method="submit_review",
            requirement_id=requirement_id,
            expected_version=expected_version,
            assigned_to_employee_id=assigned_to_employee_id,
            action_token=action_token,
        )

    async def resubmit_review(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        return await self._transition(
            RequirementStatus.REJECTED,
            method="resubmit_review",
            requirement_id=requirement_id,
            expected_version=expected_version,
            assigned_to_employee_id=assigned_to_employee_id,
            action_token=action_token,
        )

    def _require_manager_access(self, detail: RequirementDetail) -> None:
        if self.current_user.status != "ACTIVE" or not any(
            role.role_code is RoleCode.BUILDING_MANAGER for role in self.current_user.roles
        ):
            raise PermissionDeniedError("PERMISSION_DENIED", "当前用户不是有效楼长")
        if detail.building.building_id not in {
            building.building_id for building in self.current_user.buildings
        }:
            raise PermissionDeniedError("PERMISSION_DENIED", "采购申请不在楼长负责楼宇")
        if (
            detail.current_handler is None
            or detail.current_handler.employee_id != self.current_user.employee_id
        ):
            raise InvalidHandlerError("INVALID_HANDLER", "当前用户不是处理人")

    async def update_review_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: ReviewFieldsPatch,
    ) -> ReviewFieldsSaveResult:
        self._record("update_review_fields")
        detail = self._require_requirement(requirement_id)
        self._require_manager_access(detail)
        if detail.status is not RequirementStatus.PENDING_REVIEW:
            raise InvalidStatusError("INVALID_STATUS", "当前状态不可保存审核字段")
        if detail.version != expected_version:
            raise ConcurrentModificationError("CONCURRENT_MODIFICATION", "版本冲突")
        current = detail.review_fields or ReviewFields()
        merged = current.model_copy(update=fields.provided_fields())
        if merged.estimated_unit_price is not None and detail.applicant_fields.quantity is not None:
            merged = merged.model_copy(
                update={
                    "estimated_total_price": str(
                        Decimal(merged.estimated_unit_price)
                        * Decimal(detail.applicant_fields.quantity)
                    )
                }
            )
        required = (
            "proposed_supplier_id",
            "supplier_contact_name",
            "supplier_contact_info",
            "estimated_unit_price",
            "need_contract",
            "payment_method",
            "expected_arrival_date",
        )
        missing = [name for name in required if getattr(merged, name) in (None, "")]
        if merged.need_contract is True and not merged.contract_type:
            missing.append("contract_type")
        updated = detail.model_copy(
            update={
                "review_fields": merged,
                "review_record": ReviewRecordSummary(review_status=ReviewStatus.DRAFT),
                "version": detail.version + 1,
                "missing_fields": tuple(missing),
                "fields_complete": not missing,
                "allowed_actions": (
                    AllowedRequirementAction.UPDATE_REVIEW_FIELDS,
                    AllowedRequirementAction.REJECT,
                    *((AllowedRequirementAction.SUBMIT_PURCHASER,) if not missing else ()),
                ),
            }
        )
        self._requirements[requirement_id] = updated
        return ReviewFieldsSaveResult(
            requirement_id=requirement_id,
            status=updated.status,
            version=updated.version,
            review_fields=merged,
            review_record=updated.review_record,
            missing_fields=tuple(missing),
            fields_complete=not missing,
        )

    async def reject_requirement(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        reason: str,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        self._record("reject_requirement")
        duplicate = self._action_results.get(action_token)
        if duplicate is not None:
            raise DuplicateOperationError("DUPLICATE_OPERATION", "操作已执行")
        detail = self._require_requirement(requirement_id)
        self._require_manager_access(detail)
        if not reason.strip():
            raise MissingRequiredFieldsError("MISSING_REQUIRED_FIELDS", "驳回原因必填")
        if detail.status is not RequirementStatus.PENDING_REVIEW:
            raise InvalidStatusError("INVALID_STATUS", "当前状态不可驳回")
        if detail.version != expected_version:
            raise ConcurrentModificationError("CONCURRENT_MODIFICATION", "版本冲突")
        updated = detail.model_copy(
            update={
                "status": RequirementStatus.REJECTED,
                "version": detail.version + 1,
                "current_handler": None,
                "rejection_reason": reason.strip(),
                "review_record": ReviewRecordSummary(review_status=ReviewStatus.COMPLETED),
                "allowed_actions": (),
            }
        )
        self._requirements[requirement_id] = updated
        result = RequirementTransitionResult(
            requirement_id=updated.requirement_id,
            requirement_no=updated.requirement_no,
            status=updated.status,
            version=updated.version,
            current_handler=None,
            action_token=action_token,
        )
        self._action_results[action_token] = result
        return result

    async def submit_purchaser(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        self._record("submit_purchaser")
        duplicate = self._action_results.get(action_token)
        if duplicate is not None:
            raise DuplicateOperationError("DUPLICATE_OPERATION", "操作已执行")
        detail = self._require_requirement(requirement_id)
        self._require_manager_access(detail)
        if detail.status is not RequirementStatus.PENDING_REVIEW:
            raise InvalidStatusError("INVALID_STATUS", "当前状态不可提交采购员")
        if detail.version != expected_version:
            raise ConcurrentModificationError("CONCURRENT_MODIFICATION", "版本冲突")
        if not detail.fields_complete:
            raise MissingRequiredFieldsError("MISSING_REQUIRED_FIELDS", "审核字段不完整")
        candidate = next(
            (
                item
                for item in self.handler_candidates.items
                if item.employee_id == assigned_to_employee_id
            ),
            None,
        )
        if candidate is None:
            raise InvalidHandlerError("INVALID_HANDLER", "处理人不在采购员候选列表")
        updated = detail.model_copy(
            update={
                "status": RequirementStatus.PENDING_PURCHASE,
                "version": detail.version + 1,
                "current_handler": RequirementHandler(
                    employee_id=candidate.employee_id, name=candidate.name
                ),
                "review_record": ReviewRecordSummary(review_status=ReviewStatus.COMPLETED),
                "allowed_actions": (),
            }
        )
        self._requirements[requirement_id] = updated
        result = RequirementTransitionResult(
            requirement_id=updated.requirement_id,
            requirement_no=updated.requirement_no,
            status=updated.status,
            version=updated.version,
            current_handler=updated.current_handler,
            action_token=action_token,
        )
        self._action_results[action_token] = result
        return result

    async def get_or_create_agent_conversation(
        self, *, identity: PlatformIdentity, current_action: str
    ) -> AgentConversation:
        self._record("get_or_create_agent_conversation")
        for conversation in self._conversations.values():
            if (
                conversation.current_action == current_action
                and conversation.status is AgentConversationStatus.ACTIVE
            ):
                return conversation
        now = datetime.now(UTC)
        conversation_id = self._next_conversation_id
        self._next_conversation_id += 1
        conversation = AgentConversation(
            conversation_id=conversation_id,
            current_action=current_action,
            status=AgentConversationStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        self._conversations[conversation_id] = conversation
        self._messages[conversation_id] = []
        return conversation

    def _require_conversation(self, conversation_id: int) -> AgentConversation:
        try:
            return self._conversations[conversation_id]
        except KeyError as exc:
            raise SessionNotFoundError("SESSION_NOT_FOUND", "会话不存在") from exc

    async def append_agent_message(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
        sender_type: AgentMessageSender,
        content: str,
    ) -> AgentMessageWriteResult:
        self._record("append_agent_message", conversation_id)
        self._require_conversation(conversation_id)
        duplicate = self._external_ids.get((conversation_id, external_message_id))
        if duplicate is not None:
            return duplicate.model_copy(update={"duplicate": True})
        created_at = datetime.now(UTC)
        message_id = self._next_message_id
        self._next_message_id += 1
        message = AgentMessage(
            message_id=message_id,
            conversation_id=conversation_id,
            external_message_id=external_message_id,
            sender_type=sender_type,
            content=content,
            created_at=created_at,
        )
        self._messages[conversation_id].append(message)
        result = AgentMessageWriteResult(
            message_id=message_id,
            created_at=created_at,
            duplicate=False,
        )
        self._external_ids[(conversation_id, external_message_id)] = result
        return result

    async def list_agent_messages(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> AgentMessagePage:
        self._record("list_agent_messages", conversation_id)
        self._require_conversation(conversation_id)
        if page < 1 or not 1 <= page_size <= 200:
            raise ValueError("invalid pagination")
        messages = self._messages[conversation_id]
        start = (page - 1) * page_size
        return AgentMessagePage(
            items=tuple(messages[start : start + page_size]),
            page=page,
            page_size=page_size,
            total=len(messages),
        )

    async def get_agent_state(
        self, *, identity: PlatformIdentity, conversation_id: int
    ) -> AgentSessionState:
        self._record("get_agent_state", conversation_id)
        self._require_conversation(conversation_id)
        try:
            return self._states[conversation_id]
        except KeyError as exc:
            raise SessionNotFoundError("SESSION_NOT_FOUND", "会话状态不存在") from exc

    async def update_agent_state(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        state: AgentSessionStateUpdate,
    ) -> AgentStateSaveResult:
        self._record("update_agent_state", conversation_id)
        self._require_conversation(conversation_id)
        now = datetime.now(UTC)
        saved = AgentSessionState(
            conversation_id=conversation_id,
            expires_in_seconds=259200,
            **state.model_dump(),
        )
        self._states[conversation_id] = saved
        return AgentStateSaveResult(
            conversation_id=conversation_id,
            expires_in_seconds=saved.expires_in_seconds,
            updated_at=now,
        )

    async def snapshot_agent_state(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        snapshot_reason: str,
    ) -> AgentSessionSnapshot:
        self._record("snapshot_agent_state", conversation_id)
        self._require_conversation(conversation_id)
        snapshot = AgentSessionSnapshot(
            snapshot_id=len(self.snapshots) + 1,
            conversation_id=conversation_id,
            snapshot_reason=snapshot_reason,
            created_at=datetime.now(UTC),
        )
        self.snapshots.append(snapshot)
        return snapshot

    async def complete_agent_conversation(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        purchase_request_id: int | None,
    ) -> AgentConversationCompletion:
        self._record("complete_agent_conversation", conversation_id)
        conversation = self._require_conversation(conversation_id)
        now = datetime.now(UTC)
        self._conversations[conversation_id] = conversation.model_copy(
            update={"status": AgentConversationStatus.COMPLETED, "updated_at": now}
        )
        deleted = self._states.pop(conversation_id, None) is not None
        return AgentConversationCompletion(
            conversation_id=conversation_id,
            status=AgentConversationStatus.COMPLETED,
            redis_state_deleted=deleted,
            completed_at=now,
        )

    async def aclose(self) -> None:
        self._record("aclose")
