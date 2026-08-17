from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
    RequirementNotFoundError,
    SessionNotFoundError,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    ApplicantFields,
    ApplicantFieldsPatch,
    ApplicantFieldsSaveResult,
    HandlerCandidates,
    ProductRecommendations,
    PurchaseFields,
    PurchaseFieldsPatch,
    PurchaseFieldsSaveResult,
    PurchaseHistoryRecommendations,
    PurchaseRecord,
    PurchaseRecordPage,
    RequirementBuilding,
    RequirementCompletionResult,
    RequirementDetail,
    RequirementHandler,
    RequirementListItem,
    RequirementPage,
    RequirementSummary,
    RequirementTimeline,
    RequirementTransitionResult,
    ReviewFields,
    ReviewFieldsPatch,
    ReviewFieldsSaveResult,
    ReviewRecordSummary,
    SupplierDetail,
    SupplierPage,
    SupplierRecommendation,
    SupplierRecommendations,
    SupplierSummary,
    SupplierUpsertCommand,
    TimelineContact,
    WarehouseFields,
    WarehouseFieldsPatch,
    WarehouseFieldsSaveResult,
)
from procurement_platform.domain.user import CurrentUser


@dataclass(frozen=True, slots=True)
class FakeCall:
    method: str
    conversation_id: int | None = None


class FakeBackendClient:
    def __init__(
        self,
        current_user: CurrentUser | None = None,
        *,
        users_by_platform_id: dict[str, CurrentUser] | None = None,
    ) -> None:
        if current_user is None and not users_by_platform_id:
            raise ValueError("at least one fake user is required")
        self.current_user = current_user or next(iter((users_by_platform_id or {}).values()))
        self._users_by_platform_id = dict(users_by_platform_id or {})
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
        self.handler_candidates_by_role: dict[RoleCode, HandlerCandidates] = {}
        self._action_results: dict[UUID, RequirementTransitionResult] = {}
        self._completion_results: dict[UUID, RequirementCompletionResult] = {}
        self._next_requirement_id = 1
        self._suppliers: dict[int, SupplierDetail] = {}
        self._next_supplier_id = 1
        self.purchase_records: list[PurchaseRecord] = []
        self.timelines: dict[int, RequirementTimeline] = {}
        self.timeline_contacts: dict[tuple[int, int, str], TimelineContact] = {}
        self.product_recommendations = ProductRecommendations(items=())
        self.purchase_history_recommendations = PurchaseHistoryRecommendations(items=())

    def seed_supplier(self, supplier: SupplierDetail) -> None:
        self._suppliers[supplier.supplier_id] = supplier
        self._next_supplier_id = max(self._next_supplier_id, supplier.supplier_id + 1)

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
        return self._user(identity)

    def _user(self, identity: PlatformIdentity) -> CurrentUser:
        if not self._users_by_platform_id:
            return self.current_user
        try:
            return self._users_by_platform_id[identity.platform_user_id]
        except KeyError as exc:
            raise PermissionDeniedError(
                "FAKE_USER_NOT_MAPPED", "当前飞书账号尚未配置 Fake 身份"
            ) from exc

    def seed_requirement(self, detail: RequirementDetail) -> None:
        self._requirements[detail.requirement_id] = detail
        self._next_requirement_id = max(self._next_requirement_id, detail.requirement_id + 1)

    async def create_requirement(
        self, *, identity: PlatformIdentity, building_id: int
    ) -> RequirementSummary:
        self._record("create_requirement")
        current_user = self._user(identity)
        building = next(
            (item for item in current_user.buildings if item.building_id == building_id),
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
        current_user = self._user(identity)
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
                    and item.current_handler.employee_id == current_user.employee_id
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
                device_name=item.applicant_fields.device_name,
                current_handler_name=(
                    item.current_handler.name if item.current_handler is not None else None
                ),
            )
            for item in values[start : start + page_size]
        )
        return RequirementPage(items=items, page=page, page_size=page_size, total=len(values))

    async def get_requirement_timeline(
        self, *, identity: PlatformIdentity, requirement_id: int
    ) -> RequirementTimeline:
        self._record("get_requirement_timeline")
        self._user(identity)
        self._require_requirement(requirement_id)
        return self.timelines.get(requirement_id, RequirementTimeline(items=()))

    async def get_timeline_contact(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        log_id: int,
        subject: str = "operator",
    ) -> TimelineContact:
        self._record("get_timeline_contact")
        self._user(identity)
        timeline = self.timelines.get(requirement_id, RequirementTimeline(items=()))
        item = next((entry for entry in timeline.items if entry.log_id == log_id), None)
        if item is None:
            raise RequirementNotFoundError("TIMELINE_ITEM_NOT_FOUND", "流程记录不存在")
        configured = self.timeline_contacts.get((requirement_id, log_id, subject))
        if configured is not None:
            return configured
        if subject == "assignee":
            return TimelineContact(
                employee_name=item.assigned_to_name or "-",
                mobile=item.assigned_to_mobile_masked,
            )
        return TimelineContact(
            employee_name=item.operator_name,
            mobile=item.operator_mobile_masked,
        )

    async def list_purchase_records(
        self,
        *,
        identity: PlatformIdentity,
        requirement_no: str | None = None,
        supplier_id: int | None = None,
        status: RequirementStatus | None = None,
        device_name: str | None = None,
        brand: str | None = None,
        model: str | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PurchaseRecordPage:
        self._record("list_purchase_records")
        self._user(identity)
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("invalid pagination")
        records = [
            item
            for item in self.purchase_records
            if (requirement_no is None or item.requirement_no == requirement_no)
            and (supplier_id is None or item.supplier_id == supplier_id)
            and (status is None or item.status is status)
            and (
                device_name is None or device_name.casefold() in (item.device_name or "").casefold()
            )
            and (brand is None or brand.casefold() in (item.brand or "").casefold())
            and (model is None or model.casefold() in (item.model or "").casefold())
            and (created_from is None or item.created_at.date() >= created_from)
            and (created_to is None or item.created_at.date() <= created_to)
        ]
        start = (page - 1) * page_size
        return PurchaseRecordPage(
            items=tuple(records[start : start + page_size]),
            page=page,
            page_size=page_size,
            total=len(records),
        )

    async def recommend_products(
        self,
        *,
        identity: PlatformIdentity,
        device_name: str,
        device_profession: str | None = None,
        keyword: str | None = None,
        limit: int = 3,
    ) -> ProductRecommendations:
        self._record("recommend_products")
        self._user(identity)
        del device_profession
        if not device_name.strip() or not 1 <= limit <= 30:
            raise ValueError("invalid product recommendation query")
        items = self.product_recommendations.items
        if keyword:
            key = keyword.casefold()
            items = tuple(
                item
                for item in items
                if key in (item.brand or "").casefold() or key in (item.model or "").casefold()
            )
        return ProductRecommendations(items=items[:limit])

    async def recommend_purchase_history(
        self, *, identity: PlatformIdentity, requirement_id: int, limit: int = 10
    ) -> PurchaseHistoryRecommendations:
        self._record("recommend_purchase_history")
        self._user(identity)
        self._require_requirement(requirement_id)
        return PurchaseHistoryRecommendations(
            items=self.purchase_history_recommendations.items[:limit]
        )

    async def list_handler_candidates(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        target_role: RoleCode,
    ) -> HandlerCandidates:
        self._record("list_handler_candidates")
        self._require_requirement(requirement_id)
        if target_role not in {
            RoleCode.BUILDING_MANAGER,
            RoleCode.PURCHASER,
            RoleCode.WAREHOUSE_MANAGER,
        }:
            raise ValueError("unsupported target role")
        return self.handler_candidates_by_role.get(target_role, self.handler_candidates)

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

    def _require_manager_access(self, detail: RequirementDetail, current_user: CurrentUser) -> None:
        if current_user.status != "ACTIVE" or not any(
            role.role_code is RoleCode.BUILDING_MANAGER for role in current_user.roles
        ):
            raise PermissionDeniedError("PERMISSION_DENIED", "当前用户不是有效楼长")
        if detail.building.building_id not in {
            building.building_id for building in current_user.buildings
        }:
            raise PermissionDeniedError("PERMISSION_DENIED", "采购申请不在楼长负责楼宇")
        if (
            detail.current_handler is None
            or detail.current_handler.employee_id != current_user.employee_id
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
        self._require_manager_access(detail, self._user(identity))
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
            "proposed_supplier_name",
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
        self._require_manager_access(detail, self._user(identity))
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
        self._require_manager_access(detail, self._user(identity))
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

    def _require_purchaser_access(
        self, detail: RequirementDetail, current_user: CurrentUser
    ) -> None:
        if current_user.status != "ACTIVE" or not any(
            role.role_code is RoleCode.PURCHASER for role in current_user.roles
        ):
            raise PermissionDeniedError("PERMISSION_DENIED", "当前用户不是有效采购员")
        if (
            detail.current_handler is None
            or detail.current_handler.employee_id != current_user.employee_id
        ):
            raise InvalidHandlerError("INVALID_HANDLER", "当前用户不是采购单处理人")

    async def start_purchase(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        self._record("start_purchase")
        if action_token in self._action_results:
            raise DuplicateOperationError("DUPLICATE_OPERATION", "操作已执行")
        detail = self._require_requirement(requirement_id)
        self._require_purchaser_access(detail, self._user(identity))
        if detail.status is not RequirementStatus.PENDING_PURCHASE:
            raise InvalidStatusError("INVALID_STATUS", "当前状态不能开始采购")
        if detail.version != expected_version:
            raise ConcurrentModificationError("CONCURRENT_MODIFICATION", "版本冲突")
        updated = detail.model_copy(
            update={
                "status": RequirementStatus.PURCHASING,
                "version": detail.version + 1,
                "allowed_actions": (AllowedRequirementAction.UPDATE_PURCHASE_FIELDS,),
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

    async def search_suppliers(
        self,
        *,
        identity: PlatformIdentity,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
    ) -> SupplierPage:
        self._record("search_suppliers")
        if not keyword.strip():
            raise ValueError("keyword must not be empty")
        matches = [
            item
            for item in self._suppliers.values()
            if keyword.casefold() in item.supplier_name.casefold()
            or (item.supplier_tax_number is not None and keyword == item.supplier_tax_number)
        ]
        start = (page - 1) * page_size
        return SupplierPage(
            items=tuple(
                SupplierSummary.model_validate(
                    item.model_dump(
                        include={"supplier_id", "supplier_name", "supplier_tax_number", "blacklist"}
                    )
                )
                for item in matches[start : start + page_size]
            ),
            page=page,
            page_size=page_size,
            total=len(matches),
        )

    async def get_supplier(
        self,
        *,
        identity: PlatformIdentity,
        supplier_id: int,
    ) -> SupplierDetail:
        self._record("get_supplier")
        try:
            return self._suppliers[supplier_id]
        except KeyError as exc:
            raise BackendApplicationError("SUPPLIER_NOT_FOUND", "供应商不存在") from exc

    async def recommend_suppliers(
        self, *, identity: PlatformIdentity, requirement_id: int, limit: int = 3
    ) -> SupplierRecommendations:
        self._record("recommend_suppliers")
        if not 1 <= limit <= 30:
            raise ValueError("limit must be between 1 and 30")
        detail = self._require_requirement(requirement_id)
        self._require_manager_access(detail, self._user(identity))
        if detail.status is not RequirementStatus.PENDING_REVIEW:
            raise InvalidStatusError("INVALID_STATUS", "当前状态不可推荐供应商")
        return SupplierRecommendations(
            items=tuple(
                SupplierRecommendation(
                    supplier_id=supplier.supplier_id,
                    supplier_name=supplier.supplier_name,
                    historical_purchase_count=sum(
                        1
                        for record in self.purchase_records
                        if record.supplier_id == supplier.supplier_id
                    ),
                    last_purchase_at=max(
                        (
                            record.purchased_at
                            for record in self.purchase_records
                            if record.supplier_id == supplier.supplier_id
                            and record.purchased_at is not None
                        ),
                        default=datetime(1970, 1, 1, tzinfo=UTC),
                    ),
                    blacklist_status="BLACKLISTED"
                    if supplier.blacklist and supplier.blacklist.active
                    else "NORMAL",
                )
                for supplier in self._suppliers.values()
                if supplier.blacklist is None or not supplier.blacklist.active
            )[:limit]
        )

    async def create_supplier(
        self,
        *,
        identity: PlatformIdentity,
        command: SupplierUpsertCommand,
    ) -> SupplierSummary:
        self._record("create_supplier")
        conflict = next(
            (
                item
                for item in self._suppliers.values()
                if item.supplier_name == command.supplier_name
                or (
                    command.supplier_tax_number is not None
                    and item.supplier_tax_number == command.supplier_tax_number
                )
            ),
            None,
        )
        if conflict is not None:
            raise BackendApplicationError("SUPPLIER_MATCH_CONFLICT", "供应商匹配冲突")
        supplier = SupplierDetail(
            supplier_id=self._next_supplier_id, **command.model_dump(), bank_account_masked=False
        )
        self._next_supplier_id += 1
        self._suppliers[supplier.supplier_id] = supplier
        return SupplierSummary.model_validate(
            supplier.model_dump(
                include={"supplier_id", "supplier_name", "supplier_tax_number", "blacklist"}
            )
        )

    async def update_purchase_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: PurchaseFieldsPatch,
    ) -> PurchaseFieldsSaveResult:
        self._record("update_purchase_fields")
        detail = self._require_requirement(requirement_id)
        self._require_purchaser_access(detail, self._user(identity))
        if detail.status is not RequirementStatus.PURCHASING:
            raise InvalidStatusError("INVALID_STATUS", "当前状态不能保存采购字段")
        if detail.version != expected_version:
            raise ConcurrentModificationError("CONCURRENT_MODIFICATION", "版本冲突")
        current = detail.purchase_fields or PurchaseFields()
        merged = current.model_copy(update=fields.provided_fields())
        if merged.actual_unit_price and detail.applicant_fields.quantity:
            merged = merged.model_copy(
                update={
                    "actual_total_price": str(
                        Decimal(merged.actual_unit_price)
                        * Decimal(detail.applicant_fields.quantity)
                    )
                }
            )
        required = (
            "supplier_id",
            "supplier_tax_number",
            "bank_name",
            "bank_account",
            "registered_address",
            "contract_contact_info",
            "actual_unit_price",
            "tax_rate",
            "purchased_at",
        )
        missing = tuple(name for name in required if getattr(merged, name) in (None, ""))
        actions = [AllowedRequirementAction.UPDATE_PURCHASE_FIELDS]
        if not missing:
            actions.append(AllowedRequirementAction.SUBMIT_WAREHOUSE)
        updated = detail.model_copy(
            update={
                "purchase_fields": merged,
                "version": detail.version + 1,
                "missing_fields": missing,
                "fields_complete": not missing,
                "allowed_actions": tuple(actions),
            }
        )
        self._requirements[requirement_id] = updated
        return PurchaseFieldsSaveResult(
            requirement_id=requirement_id,
            status=updated.status,
            version=updated.version,
            purchase_fields=merged,
            missing_fields=missing,
            fields_complete=not missing,
        )

    async def submit_warehouse(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        assigned_to_employee_id: int,
        action_token: UUID,
    ) -> RequirementTransitionResult:
        self._record("submit_warehouse")
        if action_token in self._action_results:
            raise DuplicateOperationError("DUPLICATE_OPERATION", "操作已执行")
        detail = self._require_requirement(requirement_id)
        self._require_purchaser_access(detail, self._user(identity))
        if detail.status is not RequirementStatus.PURCHASING:
            raise InvalidStatusError("INVALID_STATUS", "当前状态不能提交仓库")
        if detail.version != expected_version:
            raise ConcurrentModificationError("CONCURRENT_MODIFICATION", "版本冲突")
        if not detail.fields_complete:
            raise MissingRequiredFieldsError("MISSING_REQUIRED_FIELDS", "采购字段不完整")
        candidate = next(
            (
                item
                for item in self.handler_candidates.items
                if item.employee_id == assigned_to_employee_id
            ),
            None,
        )
        if candidate is None:
            raise InvalidHandlerError("INVALID_HANDLER", "处理人不在仓库管理员候选列表")
        updated = detail.model_copy(
            update={
                "status": RequirementStatus.PENDING_WAREHOUSE,
                "version": detail.version + 1,
                "current_handler": RequirementHandler(
                    employee_id=candidate.employee_id, name=candidate.name
                ),
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

    def _require_warehouse_access(
        self, detail: RequirementDetail, current_user: CurrentUser
    ) -> None:
        if current_user.status != "ACTIVE" or not any(
            role.role_code is RoleCode.WAREHOUSE_MANAGER for role in current_user.roles
        ):
            raise PermissionDeniedError("PERMISSION_DENIED", "当前用户不是有效仓库管理员")
        if (
            detail.current_handler is None
            or detail.current_handler.employee_id != current_user.employee_id
        ):
            raise InvalidHandlerError("INVALID_HANDLER", "当前用户不是处理人")

    async def update_warehouse_fields(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        fields: WarehouseFieldsPatch,
    ) -> WarehouseFieldsSaveResult:
        self._record("update_warehouse_fields")
        detail = self._require_requirement(requirement_id)
        self._require_warehouse_access(detail, self._user(identity))
        if detail.status is not RequirementStatus.PENDING_WAREHOUSE:
            raise InvalidStatusError("INVALID_STATUS", "当前状态不可保存入库字段")
        if detail.version != expected_version:
            raise ConcurrentModificationError("CONCURRENT_MODIFICATION", "版本冲突")
        merged = (detail.warehouse_fields or WarehouseFields()).model_copy(
            update=fields.provided_fields()
        )
        missing = [
            name
            for name in ("warehouse_location", "received_quantity")
            if getattr(merged, name) in (None, "")
        ]
        if (
            merged.received_quantity is not None
            and detail.applicant_fields.quantity is not None
            and Decimal(merged.received_quantity) < Decimal(detail.applicant_fields.quantity)
            and not merged.receipt_remark
        ):
            missing.append("receipt_remark")
        updated = detail.model_copy(
            update={
                "warehouse_fields": merged,
                "version": detail.version + 1,
                "missing_fields": tuple(missing),
                "fields_complete": not missing,
                "allowed_actions": (
                    AllowedRequirementAction.UPDATE_WAREHOUSE_FIELDS,
                    *((AllowedRequirementAction.COMPLETE,) if not missing else ()),
                ),
            }
        )
        self._requirements[requirement_id] = updated
        return WarehouseFieldsSaveResult(
            requirement_id=requirement_id,
            status=updated.status,
            version=updated.version,
            warehouse_fields=merged,
            missing_fields=tuple(missing),
            fields_complete=not missing,
        )

    async def complete_requirement(
        self,
        *,
        identity: PlatformIdentity,
        requirement_id: int,
        expected_version: int,
        action_token: UUID,
    ) -> RequirementCompletionResult:
        self._record("complete_requirement")
        duplicate = self._completion_results.get(action_token)
        if duplicate is not None:
            raise DuplicateOperationError("DUPLICATE_OPERATION", "操作已执行")
        detail = self._require_requirement(requirement_id)
        self._require_warehouse_access(detail, self._user(identity))
        if detail.status is not RequirementStatus.PENDING_WAREHOUSE:
            raise InvalidStatusError("INVALID_STATUS", "当前状态不可完成")
        if detail.version != expected_version:
            raise ConcurrentModificationError("CONCURRENT_MODIFICATION", "版本冲突")
        if not detail.fields_complete:
            raise MissingRequiredFieldsError("MISSING_REQUIRED_FIELDS", "入库字段不完整")
        completed_at = datetime.now(UTC)
        updated = detail.model_copy(
            update={
                "status": RequirementStatus.COMPLETED,
                "version": detail.version + 1,
                "current_handler": None,
                "allowed_actions": (),
                "completed_at": completed_at,
            }
        )
        self._requirements[requirement_id] = updated
        result = RequirementCompletionResult(
            requirement_id=updated.requirement_id,
            requirement_no=updated.requirement_no,
            status=updated.status,
            version=updated.version,
            current_handler=None,
            completed_at=completed_at,
            action_token=action_token,
        )
        self._completion_results[action_token] = result
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

    async def get_agent_message_by_external_id(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        external_message_id: str,
    ) -> AgentMessage | None:
        self._record("get_agent_message_by_external_id", conversation_id)
        self._user(identity)
        self._require_conversation(conversation_id)
        return next(
            (
                message
                for message in self._messages[conversation_id]
                if message.external_message_id == external_message_id
            ),
            None,
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
        saved = AgentSessionState(
            conversation_id=conversation_id,
            expires_in_seconds=259200,
            **state.model_dump(),
        )
        self._states[conversation_id] = saved
        return AgentStateSaveResult(
            saved=True,
            expires_in_seconds=saved.expires_in_seconds,
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
