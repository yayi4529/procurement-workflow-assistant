"""Task 9 domain tools shared by the optional conversational assistant."""

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from procurement_platform.application.assistant.candidate_resolver import CandidateResolver
from procurement_platform.application.assistant.exact_field_renderer import ExactFieldRenderer
from procurement_platform.application.assistant.temporal_range_resolver import (
    DateTimeRange,
    TemporalRangeResolver,
)
from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult
from procurement_platform.domain.assistant_session import (
    AgentSessionState,
    AgentSessionStateUpdate,
    JsonValue,
    RecommendationReference,
)
from procurement_platform.domain.enums import (
    PlatformType,
    RequirementStatus,
    RoleCode,
)
from procurement_platform.domain.errors import (
    BackendProtocolError,
    BackendTimeoutError,
    BackendUnavailableError,
    ConcurrentModificationError,
    InvalidHandlerError,
    PermissionDeniedError,
    SessionNotFoundError,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.interaction import (
    ActionButton,
    InteractionView,
    KeyValueField,
    KeyValueSection,
)
from procurement_platform.domain.notification import (
    InteractionNotification,
    NotificationGatewayRequest,
)
from procurement_platform.domain.requirement import (
    ApplicantFieldsPatch,
    ProductRecommendation,
    PurchaseFields,
    PurchaseFieldsPatch,
    PurchaseRecord,
    RequirementDetail,
    ReviewFieldsPatch,
    SupplierDetail,
    WarehouseFieldsPatch,
)
from procurement_platform.domain.user import CurrentUser
from procurement_platform.ports.backend_client import BackendClient

ToolOperation = Literal["SEARCH", "GET_DETAIL", "GET_TIMELINE"]
TimeField = Literal[
    "CREATED_AT",
    "SUBMITTED_AT",
    "APPROVED_AT",
    "REJECTED_AT",
    "PURCHASED_AT",
    "WAREHOUSE_SUBMITTED_AT",
    "COMPLETED_AT",
]
SupplierProfileField = Literal[
    "UNIFIED_SOCIAL_CREDIT_CODE",
    "BANK_NAME",
    "BANK_ACCOUNT",
    "REGISTERED_ADDRESS",
    "CONTRACT_CONTACT_INFO",
    "BLACKLIST_STATUS",
]


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _identity(context: AssistantToolContext) -> PlatformIdentity:
    return PlatformIdentity.create(PlatformType(context.platform_type), context.platform_user_id)


async def _active_user(
    backend: BackendClient, context: AssistantToolContext, role: RoleCode
) -> tuple[PlatformIdentity, CurrentUser] | None:
    identity = _identity(context)
    user = await backend.get_current_user(identity=identity)
    if user.status != "ACTIVE" or role not in {item.role_code for item in user.roles}:
        return None
    return identity, user


def _is_handler(detail: RequirementDetail, user: CurrentUser) -> bool:
    return (
        detail.current_handler is not None
        and detail.current_handler.employee_id == user.employee_id
    )


def _backend_failure(result_type: type[AssistantToolResult]) -> AssistantToolResult:
    return result_type(status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用")


class SessionReferenceStore:
    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def state(self, identity: PlatformIdentity, conversation_id: int) -> AgentSessionState:
        return await self._backend.get_agent_state(
            identity=identity, conversation_id=conversation_id
        )

    async def save(
        self,
        *,
        identity: PlatformIdentity,
        context: AssistantToolContext,
        requirement_id: int | None,
        references: tuple[RecommendationReference, ...] = (),
        focused_role: RoleCode | None = None,
        focused_field: str | None = None,
        missing_fields: tuple[str, ...] | None = None,
        pending_field: str | None = None,
        collected_data: dict[str, JsonValue] | None = None,
        awaiting_confirmation: bool = False,
        clear_recommendations: bool = False,
    ) -> str:
        try:
            current = await self.state(identity, context.conversation_id)
            update = AgentSessionStateUpdate.model_validate(
                current.model_dump(
                    exclude={"conversation_id", "expires_in_seconds", "restored_from_snapshot"}
                )
            )
        except SessionNotFoundError:
            update = AgentSessionStateUpdate()
        candidate_set_id = f"candidates:{context.conversation_id}:{context.external_message_id}"
        merged_data = dict(update.collected_data)
        if collected_data:
            merged_data.update(collected_data)
        await self._backend.update_agent_state(
            identity=identity,
            conversation_id=context.conversation_id,
            state=update.model_copy(
                update={
                    "purchase_request_id": requirement_id,
                    "collected_data": merged_data,
                    "missing_fields": (
                        missing_fields if missing_fields is not None else update.missing_fields
                    ),
                    "pending_field": pending_field,
                    "last_recommendations": () if clear_recommendations else references,
                    "focused_role": focused_role,
                    "focused_field": focused_field,
                    "awaiting_confirmation": awaiting_confirmation,
                }
            ),
        )
        return candidate_set_id


class PurchaseRequestCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_ref: str
    requirement_id: int
    requirement_no: str
    device_name: str | None
    status: RequirementStatus
    current_handler_name: str | None = None
    matched_at: datetime | None = None


class QueryPurchaseRequestsArgs(StrictArgs):
    operation: ToolOperation
    requirement_id: int | None = Field(default=None, gt=0)
    time_expression: str | None = Field(default=None, max_length=50)
    time_field: TimeField = "CREATED_AT"
    device_name: str | None = Field(default=None, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=150)
    status: RequirementStatus | None = None
    result_limit: int = Field(default=10, ge=1, le=20)

    @model_validator(mode="after")
    def validate_operation(self) -> "QueryPurchaseRequestsArgs":
        if self.operation != "SEARCH" and self.requirement_id is None:
            raise ValueError("requirement_id is required for detail or timeline")
        return self


class QueryPurchaseRequestsResult(AssistantToolResult):
    records: tuple[PurchaseRequestCandidate, ...] = ()
    timeline: tuple[str, ...] = ()
    requirement_no: str | None = None
    status_value: RequirementStatus | None = None
    current_handler_name: str | None = None
    missing_fields: tuple[str, ...] = ()


class QueryPurchaseRequestsTool:
    name = "query_purchase_requests"
    description = "Query visible purchase requests, details, current handler, or timeline."
    args_model = QueryPurchaseRequestsArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._temporal = TemporalRangeResolver()
        self._session = SessionReferenceStore(backend)

    async def execute(
        self, *, args: QueryPurchaseRequestsArgs, context: AssistantToolContext
    ) -> QueryPurchaseRequestsResult:
        identity = _identity(context)
        try:
            await self._backend.get_current_user(identity=identity)
            if args.operation == "GET_DETAIL":
                return self._detail(
                    await self._backend.get_requirement(
                        identity=identity, requirement_id=args.requirement_id or 0
                    )
                )
            if args.operation == "GET_TIMELINE":
                timeline = await self._backend.get_requirement_timeline(
                    identity=identity, requirement_id=args.requirement_id or 0
                )
                return QueryPurchaseRequestsResult(
                    status="SUCCESS",
                    requirement_id=args.requirement_id,
                    timeline=tuple(
                        (
                            f"{item.operated_at.isoformat()} {item.action_type}: "
                            f"{item.operation_summary or item.to_status or ''}"
                        )
                        for item in timeline.items
                    ),
                )
            window = (
                self._temporal.resolve(args.time_expression, now=context.current_time)
                if args.time_expression
                else None
            )
            page = await self._backend.list_purchase_records(
                identity=identity,
                status=args.status,
                device_name=args.device_name,
                brand=args.brand,
                model=args.model,
                created_from=window.start.date()
                if window and args.time_field == "CREATED_AT"
                else None,
                created_to=(window.end_exclusive.date() - timedelta(days=1))
                if window and args.time_field == "CREATED_AT"
                else None,
                page=1,
                page_size=min(100, max(args.result_limit, 20)),
            )
            matched: list[tuple[PurchaseRecord, datetime | None]] = []
            for record in page.items:
                timestamp = await self._matched_at(identity, record, args.time_field, window)
                if window is None or timestamp is not None:
                    matched.append((record, timestamp))
                if len(matched) >= args.result_limit:
                    break
            if not matched:
                return QueryPurchaseRequestsResult(
                    status="NOT_FOUND", user_message="未找到符合条件的采购单"
                )
            if len(matched) == 1:
                return self._detail(
                    await self._backend.get_requirement(
                        identity=identity, requirement_id=matched[0][0].requirement_id
                    )
                )
            candidates = tuple(self._candidate(item, at) for item, at in matched)
            candidate_set = await self._session.save(
                identity=identity,
                context=context,
                requirement_id=None,
                references=tuple(
                    RecommendationReference(
                        reference_id=item.candidate_ref,
                        kind="PURCHASE_REQUEST",
                        label=f"{item.requirement_no} {item.device_name or ''}".strip(),
                    )
                    for item in candidates
                ),
                awaiting_confirmation=True,
            )
            return QueryPurchaseRequestsResult(
                status="MULTIPLE_MATCHES", candidate_set_id=candidate_set, records=candidates
            )
        except ValueError as exc:
            return QueryPurchaseRequestsResult(status="INVALID_ARGUMENTS", user_message=str(exc))
        except (PermissionDeniedError, InvalidHandlerError):
            return QueryPurchaseRequestsResult(
                status="PERMISSION_DENIED", user_message="无权查看该采购单"
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return QueryPurchaseRequestsResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )

    async def _matched_at(
        self,
        identity: PlatformIdentity,
        record: PurchaseRecord,
        field: TimeField,
        window: DateTimeRange | None,
    ) -> datetime | None:
        direct = {
            "CREATED_AT": record.created_at,
            "SUBMITTED_AT": record.submitted_at,
            "PURCHASED_AT": record.purchased_at,
            "WAREHOUSE_SUBMITTED_AT": record.received_at,
            "COMPLETED_AT": record.completed_at,
        }.get(field)
        if field in {"APPROVED_AT", "REJECTED_AT"}:
            timeline = await self._backend.get_requirement_timeline(
                identity=identity, requirement_id=record.requirement_id
            )
            direct = next(
                (
                    item.operated_at
                    for item in timeline.items
                    if (
                        field == "APPROVED_AT"
                        and item.from_status is RequirementStatus.PENDING_REVIEW
                        and item.to_status is RequirementStatus.PENDING_PURCHASE
                    )
                    or (field == "REJECTED_AT" and item.to_status is RequirementStatus.REJECTED)
                ),
                None,
            )
        if window is None:
            return direct
        return (
            direct if direct is not None and window.start <= direct < window.end_exclusive else None
        )

    @staticmethod
    def _candidate(record: PurchaseRecord, matched_at: datetime | None) -> PurchaseRequestCandidate:
        return PurchaseRequestCandidate(
            candidate_ref=f"requirement:{record.requirement_id}",
            requirement_id=record.requirement_id,
            requirement_no=record.requirement_no,
            device_name=record.device_name,
            status=record.status,
            matched_at=matched_at,
        )

    @staticmethod
    def _detail(detail: RequirementDetail) -> QueryPurchaseRequestsResult:
        return QueryPurchaseRequestsResult(
            status="SUCCESS",
            requirement_id=detail.requirement_id,
            requirement_version=detail.version,
            requirement_no=detail.requirement_no,
            status_value=detail.status,
            current_handler_name=detail.current_handler.name if detail.current_handler else None,
            missing_fields=detail.missing_fields,
        )


class RecommendProductOptionsArgs(StrictArgs):
    requirement_id: int | None = Field(default=None, gt=0)
    device_name: str | None = Field(default=None, max_length=200)
    device_profession: str | None = Field(default=None, max_length=100)
    keyword: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=3, ge=1, le=3)

    @model_validator(mode="after")
    def require_source(self) -> "RecommendProductOptionsArgs":
        if self.requirement_id is None and not self.device_name:
            raise ValueError("requirement_id or device_name is required")
        return self


class ProductOptionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_ref: str
    brand: str | None
    model: str | None
    historical_count: int
    last_purchased_at: datetime
    source: Literal["PRODUCT_RECOMMENDATION", "PURCHASE_HISTORY", "MERGED"]


class RecommendProductOptionsResult(AssistantToolResult):
    candidates: tuple[ProductOptionCandidate, ...] = ()
    focused_field: str | None = None


class RecommendProductOptionsTool:
    name = "recommend_product_options"
    description = "Recommend up to three product brand/model options from backend purchase history."
    args_model = RecommendProductOptionsArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)

    async def execute(
        self, *, args: RecommendProductOptionsArgs, context: AssistantToolContext
    ) -> RecommendProductOptionsResult:
        try:
            resolved = await _active_user(self._backend, context, RoleCode.APPLICANT)
            if resolved is None:
                return RecommendProductOptionsResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是有效需求人"
                )
            identity, _ = resolved
            try:
                state = await self._session.state(identity, context.conversation_id)
            except SessionNotFoundError:
                state = None
            detail = None
            device_name = args.device_name
            profession = args.device_profession
            if args.requirement_id:
                detail = await self._backend.get_requirement(
                    identity=identity, requirement_id=args.requirement_id
                )
                device_name = detail.applicant_fields.device_name
                profession = detail.applicant_fields.device_profession
            if not device_name:
                return RecommendProductOptionsResult(
                    status="NEED_MORE_INFORMATION", user_message="请先提供设备名称"
                )
            values = await self._backend.recommend_products(
                identity=identity,
                device_name=device_name,
                device_profession=profession,
                keyword=args.keyword,
                limit=30,
            )
            focused_field = state.pending_field if state else None
            selected_brand = None
            if detail is not None:
                selected_brand = detail.applicant_fields.brand
            if selected_brand is None and state is not None:
                value = state.collected_data.get("brand")
                selected_brand = value if isinstance(value, str) else None
            seen: set[str | tuple[str, str]] = set()
            candidates: list[ProductOptionCandidate] = []
            for item in values.items:
                if (
                    focused_field == "model"
                    and selected_brand
                    and ((item.brand or "").strip().casefold() != selected_brand.strip().casefold())
                ):
                    continue
                key: str | tuple[str, str]
                if focused_field == "brand":
                    key = (item.brand or "").strip().casefold()
                elif focused_field == "model":
                    key = (item.model or "").strip().casefold()
                else:
                    key = (
                        (item.brand or "").strip().casefold(),
                        (item.model or "").strip().casefold(),
                    )
                if not key:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(self._candidate(item, len(candidates) + 1))
                if len(candidates) == args.limit:
                    break
            if not candidates:
                return RecommendProductOptionsResult(
                    status="NOT_FOUND", user_message="没有历史产品推荐数据"
                )
            refs = tuple(
                RecommendationReference(
                    reference_id=item.candidate_ref,
                    kind="PRODUCT_RECOMMENDATION",
                    label=f"{item.brand or ''} {item.model or ''}".strip(),
                )
                for item in candidates
            )
            candidate_data: dict[str, JsonValue] = {
                "product_candidate_set_id": (
                    f"candidates:{context.conversation_id}:{context.external_message_id}"
                )
            }
            for candidate in candidates:
                candidate_data[f"product_candidate:{candidate.candidate_ref}:brand"] = (
                    candidate.brand
                )
                candidate_data[f"product_candidate:{candidate.candidate_ref}:model"] = (
                    candidate.model
                )
            candidate_set = await self._session.save(
                identity=identity,
                context=context,
                requirement_id=detail.requirement_id if detail else context.active_requirement_id,
                references=refs,
                focused_role=RoleCode.APPLICANT,
                focused_field=focused_field,
                pending_field=focused_field,
                missing_fields=state.missing_fields if state else None,
                collected_data=candidate_data,
                awaiting_confirmation=True,
            )
            return RecommendProductOptionsResult(
                status="SUCCESS",
                candidate_set_id=candidate_set,
                candidates=tuple(candidates),
                focused_field=focused_field,
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return RecommendProductOptionsResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )

    @staticmethod
    def _candidate(item: ProductRecommendation, index: int) -> ProductOptionCandidate:
        digest = sha256(f"{item.brand}|{item.model}".encode()).hexdigest()[:10]
        return ProductOptionCandidate(
            candidate_ref=f"product:{index}:{digest}",
            brand=item.brand,
            model=item.model,
            historical_count=item.historical_count,
            last_purchased_at=item.last_purchased_at,
            source="PRODUCT_RECOMMENDATION",
        )


class UpdatePurchaseDraftArgs(StrictArgs):
    requirement_id: int | None = Field(default=None, gt=0)
    product_ref: str | None = Field(default=None, max_length=200)
    device_profession: str | None = Field(default=None, max_length=100)
    device_name: str | None = Field(default=None, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=150)
    quantity: str | None = None
    unit: str | None = Field(default=None, max_length=30)
    application_reason: str | None = None
    applicant_remark: str | None = None


class UpdatePurchaseDraftResult(AssistantToolResult):
    requirement_no: str | None = None
    status_value: RequirementStatus | None = None
    updated_fields: tuple[str, ...] = ()
    updated_values: dict[str, str | None] = Field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()
    next_missing_field: str | None = None
    fields_complete: bool = False


class UpdatePurchaseDraftTool:
    name = "update_purchase_draft"
    description = "Create or update applicant draft fields; never submits the requirement."
    args_model = UpdatePurchaseDraftArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)

    async def execute(
        self, *, args: UpdatePurchaseDraftArgs, context: AssistantToolContext
    ) -> UpdatePurchaseDraftResult:
        try:
            resolved = await _active_user(self._backend, context, RoleCode.APPLICANT)
            if resolved is None:
                return UpdatePurchaseDraftResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是有效需求人"
                )
            identity, user = resolved
            requirement_id = args.requirement_id or context.active_requirement_id
            if requirement_id is None:
                primary = [item for item in user.buildings if item.is_primary]
                building = (
                    user.buildings[0]
                    if len(user.buildings) == 1
                    else primary[0]
                    if len(primary) == 1
                    else None
                )
                if building is None:
                    return UpdatePurchaseDraftResult(
                        status="NEED_MORE_INFORMATION", user_message="请先选择唯一所属楼宇"
                    )
                summary = await self._backend.create_requirement(
                    identity=identity, building_id=building.building_id
                )
                requirement_id = summary.requirement_id
            detail = await self._backend.get_requirement(
                identity=identity, requirement_id=requirement_id
            )
            if detail.status not in {RequirementStatus.DRAFT, RequirementStatus.REJECTED}:
                return UpdatePurchaseDraftResult(
                    status="INVALID_STATUS", user_message="当前状态不可修改需求草稿"
                )
            if (
                detail.current_handler is not None
                and detail.current_handler.employee_id != user.employee_id
            ):
                return UpdatePurchaseDraftResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是该采购单处理人"
                )
            raw = args.model_dump(exclude={"requirement_id", "product_ref"}, exclude_unset=True)
            if args.product_ref is not None:
                state = await self._session.state(identity, context.conversation_id)
                if state.pending_field not in {"brand", "model"}:
                    return UpdatePurchaseDraftResult(
                        status="INVALID_ARGUMENTS", user_message="当前没有可选择的品牌或型号候选"
                    )
                if args.product_ref not in {
                    item.reference_id
                    for item in state.last_recommendations
                    if item.kind == "PRODUCT_RECOMMENDATION"
                }:
                    return UpdatePurchaseDraftResult(
                        status="INVALID_ARGUMENTS", user_message="候选引用不存在或已过期"
                    )
                value = state.collected_data.get(
                    f"product_candidate:{args.product_ref}:{state.pending_field}"
                )
                if not isinstance(value, str) or not value.strip():
                    return UpdatePurchaseDraftResult(
                        status="INVALID_ARGUMENTS", user_message="候选不包含当前所需字段"
                    )
                raw[state.pending_field] = value
            if not raw:
                return UpdatePurchaseDraftResult(
                    status="NEED_MORE_INFORMATION", user_message="请提供需要保存的采购字段"
                )
            patch = ApplicantFieldsPatch.model_validate(raw)
            saved = await self._backend.update_applicant_fields(
                identity=identity,
                requirement_id=requirement_id,
                expected_version=detail.version,
                fields=patch,
            )
            latest = await self._backend.get_requirement(
                identity=identity, requirement_id=requirement_id
            )
            collection_missing_fields = list(saved.missing_fields)
            if not latest.applicant_fields.brand:
                collection_missing_fields.append("brand")
            elif not latest.applicant_fields.model:
                collection_missing_fields.append("model")
            next_missing_field = collection_missing_fields[0] if collection_missing_fields else None
            fields_complete = saved.fields_complete and not collection_missing_fields
            await self._session.save(
                identity=identity,
                context=context,
                requirement_id=requirement_id,
                focused_role=RoleCode.APPLICANT,
                focused_field=next_missing_field,
                missing_fields=tuple(collection_missing_fields),
                pending_field=next_missing_field,
                collected_data={key: value for key, value in raw.items()},
                awaiting_confirmation=fields_complete,
                clear_recommendations=True,
            )
            return UpdatePurchaseDraftResult(
                status="SUCCESS",
                requirement_id=requirement_id,
                requirement_version=latest.version,
                requirement_no=latest.requirement_no,
                status_value=latest.status,
                updated_fields=tuple(raw),
                updated_values={key: value for key, value in raw.items()},
                missing_fields=tuple(collection_missing_fields),
                next_missing_field=next_missing_field,
                fields_complete=fields_complete,
                user_message=(
                    "字段已完整, 请在正式需求卡片中确认并提交"
                    if fields_complete
                    else f"下一项请补充: {next_missing_field}"
                ),
            )
        except ConcurrentModificationError:
            return UpdatePurchaseDraftResult(
                status="CONCURRENT_MODIFICATION", user_message="版本已变化, 请基于最新内容重新确认"
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return UpdatePurchaseDraftResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )


class UpdateReviewDraftArgs(StrictArgs):
    requirement_id: int = Field(gt=0)
    proposed_supplier_ref: str | None = Field(default=None, max_length=200)
    supplier_contact_name: str | None = Field(default=None, max_length=100)
    supplier_contact_info: str | None = Field(default=None, max_length=255)
    supplier_link: str | None = Field(default=None, max_length=1000)
    estimated_unit_price: str | None = None
    need_contract: bool | None = None
    contract_type: str | None = Field(default=None, max_length=100)
    payment_method: str | None = Field(default=None, max_length=100)
    expected_arrival_date: date | None = None
    warranty_info: str | None = Field(default=None, max_length=255)
    review_remark: str | None = None


class UpdateReviewDraftResult(AssistantToolResult):
    updated_fields: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    fields_complete: bool = False


class UpdateReviewDraftTool:
    name = "update_review_draft"
    description = "Save building-manager review draft fields without approving or submitting."
    args_model = UpdateReviewDraftArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)
        self._resolver = CandidateResolver()

    async def execute(
        self, *, args: UpdateReviewDraftArgs, context: AssistantToolContext
    ) -> UpdateReviewDraftResult:
        try:
            resolved = await _active_user(self._backend, context, RoleCode.BUILDING_MANAGER)
            if resolved is None:
                return UpdateReviewDraftResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是有效楼长"
                )
            identity, user = resolved
            detail = await self._backend.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            if detail.status is not RequirementStatus.PENDING_REVIEW:
                return UpdateReviewDraftResult(
                    status="INVALID_STATUS", user_message="当前状态不可保存楼长草稿"
                )
            if not _is_handler(detail, user) or detail.building.building_id not in {
                item.building_id for item in user.buildings
            }:
                return UpdateReviewDraftResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是该采购单处理人"
                )
            raw = args.model_dump(
                exclude={"requirement_id", "proposed_supplier_ref"}, exclude_unset=True
            )
            if args.proposed_supplier_ref:
                state = await self._session.state(identity, context.conversation_id)
                supplier_id = self._resolver.resolve(
                    args.proposed_supplier_ref, kind="SUPPLIER_RECOMMENDATION", state=state
                )
                supplier = await self._backend.get_supplier(
                    identity=identity, supplier_id=supplier_id
                )
                if supplier.blacklist and supplier.blacklist.active:
                    return UpdateReviewDraftResult(
                        status="INVALID_STATUS", user_message="该供应商处于有效黑名单"
                    )
                raw.update(
                    {
                        "proposed_supplier_id": supplier.supplier_id,
                        "proposed_supplier_name": supplier.supplier_name,
                    }
                )
            if not raw:
                return UpdateReviewDraftResult(
                    status="NEED_MORE_INFORMATION", user_message="请提供需要保存的审核字段"
                )
            saved = await self._backend.update_review_fields(
                identity=identity,
                requirement_id=args.requirement_id,
                expected_version=detail.version,
                fields=ReviewFieldsPatch.model_validate(raw),
            )
            latest = await self._backend.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            return UpdateReviewDraftResult(
                status="SUCCESS",
                requirement_id=args.requirement_id,
                requirement_version=latest.version,
                updated_fields=tuple(raw),
                missing_fields=saved.missing_fields,
                fields_complete=saved.fields_complete,
            )
        except ValueError as exc:
            return UpdateReviewDraftResult(status="INVALID_ARGUMENTS", user_message=str(exc))
        except ConcurrentModificationError:
            return UpdateReviewDraftResult(
                status="CONCURRENT_MODIFICATION", user_message="版本已变化, 请重新确认"
            )


class QuerySupplierProfileArgs(StrictArgs):
    supplier_query: str | None = Field(default=None, max_length=200)
    supplier_ref: str | None = Field(default=None, max_length=200)
    requirement_id: int | None = Field(default=None, gt=0)
    requested_fields: tuple[SupplierProfileField, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_source(self) -> "QuerySupplierProfileArgs":
        if self.requirement_id is None and not self.supplier_ref and not self.supplier_query:
            raise ValueError("supplier source is required")
        return self


class SupplierProfileCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_ref: str
    supplier_id: int
    supplier_name: str


class QuerySupplierProfileResult(AssistantToolResult):
    supplier_id: int | None = None
    supplier_name: str | None = None
    candidates: tuple[SupplierProfileCandidate, ...] = ()
    rendered_text: str | None = None


class QuerySupplierProfileTool:
    name = "query_supplier_profile"
    description = (
        "Precisely query selected supplier master fields; exact values are rendered "
        "deterministically."
    )
    args_model = QuerySupplierProfileArgs

    _LABELS: ClassVar[dict[str, str]] = {
        "UNIFIED_SOCIAL_CREDIT_CODE": "统一社会信用代码",
        "BANK_NAME": "开户行",
        "BANK_ACCOUNT": "银行账号",
        "REGISTERED_ADDRESS": "注册地址",
        "CONTRACT_CONTACT_INFO": "合同联系方式",
        "BLACKLIST_STATUS": "黑名单状态",
    }

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._session = SessionReferenceStore(backend)

    async def execute(
        self, *, args: QuerySupplierProfileArgs, context: AssistantToolContext
    ) -> QuerySupplierProfileResult:
        resolved = await _active_user(self._backend, context, RoleCode.PURCHASER)
        if resolved is None:
            return QuerySupplierProfileResult(
                status="PERMISSION_DENIED", user_message="当前用户不是有效采购员"
            )
        identity, _ = resolved
        try:
            supplier_id: int | None = None
            requirement_id = args.requirement_id or context.active_requirement_id
            if requirement_id:
                detail = await self._backend.get_requirement(
                    identity=identity, requirement_id=requirement_id
                )
                supplier_id = (
                    detail.review_fields.proposed_supplier_id if detail.review_fields else None
                )
                if supplier_id is None:
                    return QuerySupplierProfileResult(
                        status="NOT_FOUND", user_message="该采购单尚未确定供应商"
                    )
            elif args.supplier_ref:
                state = await self._session.state(identity, context.conversation_id)
                supplier_id = CandidateResolver.resolve(
                    args.supplier_ref, kind="SUPPLIER_PROFILE", state=state
                )
            elif args.supplier_query:
                page = await self._backend.search_suppliers(
                    identity=identity, keyword=args.supplier_query, page_size=20
                )
                if not page.items:
                    return QuerySupplierProfileResult(
                        status="NOT_FOUND", user_message="未找到供应商"
                    )
                if len(page.items) > 1:
                    candidates = tuple(
                        SupplierProfileCandidate(
                            candidate_ref=f"supplier:{item.supplier_id}",
                            supplier_id=item.supplier_id,
                            supplier_name=item.supplier_name,
                        )
                        for item in page.items
                    )
                    candidate_set = await self._session.save(
                        identity=identity,
                        context=context,
                        requirement_id=requirement_id,
                        references=tuple(
                            RecommendationReference(
                                reference_id=item.candidate_ref,
                                kind="SUPPLIER_PROFILE",
                                label=item.supplier_name,
                            )
                            for item in candidates
                        ),
                        focused_role=RoleCode.PURCHASER,
                        awaiting_confirmation=True,
                    )
                    return QuerySupplierProfileResult(
                        status="MULTIPLE_MATCHES",
                        candidate_set_id=candidate_set,
                        candidates=candidates,
                    )
                supplier_id = page.items[0].supplier_id
            assert supplier_id is not None
            supplier = await self._backend.get_supplier(identity=identity, supplier_id=supplier_id)
            values = self._values(supplier)
            rendered = ExactFieldRenderer.render(
                supplier_name=supplier.supplier_name,
                fields=tuple((self._LABELS[name], values[name]) for name in args.requested_fields),
            )
            return QuerySupplierProfileResult(
                status="SUCCESS",
                supplier_id=supplier.supplier_id,
                supplier_name=supplier.supplier_name,
                exact_render_required=True,
                rendered_text=rendered,
                user_message=rendered,
            )
        except ValueError as exc:
            return QuerySupplierProfileResult(status="INVALID_ARGUMENTS", user_message=str(exc))

    @staticmethod
    def _values(supplier: SupplierDetail) -> dict[str, str | None]:
        return {
            "UNIFIED_SOCIAL_CREDIT_CODE": supplier.supplier_tax_number,
            "BANK_NAME": supplier.bank_name,
            "BANK_ACCOUNT": supplier.bank_account,
            "REGISTERED_ADDRESS": supplier.registered_address,
            "CONTRACT_CONTACT_INFO": supplier.contract_contact_info,
            "BLACKLIST_STATUS": "ACTIVE"
            if supplier.blacklist and supplier.blacklist.active
            else "INACTIVE",
        }


class PreparePurchasePrefillArgs(StrictArgs):
    requirement_id: int = Field(gt=0)


class PurchasePrefillField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    field_name: str
    value: str | None
    resolution: Literal["EXACT", "RECOMMENDED", "AMBIGUOUS", "MISSING"]
    source: Literal["REQUIREMENT", "SUPPLIER_MASTER", "PURCHASE_HISTORY"]
    evidence_count: int = 0
    alternatives: tuple[str, ...] = ()


class PreparePurchasePrefillResult(AssistantToolResult):
    supplier_id: int | None = None
    supplier_name: str | None = None
    fields: tuple[PurchasePrefillField, ...] = ()


class PurchasePrefillService:
    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def prepare(
        self, *, identity: PlatformIdentity, user: CurrentUser, requirement_id: int
    ) -> PreparePurchasePrefillResult:
        detail = await self._backend.get_requirement(
            identity=identity, requirement_id=requirement_id
        )
        if detail.status not in {RequirementStatus.PENDING_PURCHASE, RequirementStatus.PURCHASING}:
            return PreparePurchasePrefillResult(
                status="INVALID_STATUS", user_message="当前状态不能生成采购预填"
            )
        if not _is_handler(detail, user):
            return PreparePurchasePrefillResult(
                status="PERMISSION_DENIED", user_message="当前用户不是该采购单处理人"
            )
        supplier_id = detail.review_fields.proposed_supplier_id if detail.review_fields else None
        if supplier_id is None:
            return PreparePurchasePrefillResult(
                status="NOT_FOUND", user_message="楼长尚未确定供应商"
            )
        supplier = await self._backend.get_supplier(identity=identity, supplier_id=supplier_id)
        history = await self._backend.recommend_purchase_history(
            identity=identity, requirement_id=requirement_id, limit=10
        )
        snapshots: list[PurchaseFields] = []
        for item in history.items[:10]:
            historical = await self._backend.get_requirement(
                identity=identity, requirement_id=item.requirement_id
            )
            if historical.purchase_fields:
                snapshots.append(historical.purchase_fields)
        master = {
            "supplier_name": supplier.supplier_name,
            "supplier_tax_number": supplier.supplier_tax_number,
            "bank_name": supplier.bank_name,
            "bank_account": supplier.bank_account,
            "registered_address": supplier.registered_address,
            "contract_contact_info": supplier.contract_contact_info,
        }
        fields = [self._field(name, value, snapshots) for name, value in master.items()]
        fields.append(self._history_field("tax_rate", snapshots))
        return PreparePurchasePrefillResult(
            status="SUCCESS",
            requirement_id=requirement_id,
            requirement_version=detail.version,
            supplier_id=supplier.supplier_id,
            supplier_name=supplier.supplier_name,
            fields=tuple(fields),
        )

    def _field(
        self, name: str, master_value: str | None, snapshots: list[PurchaseFields]
    ) -> PurchasePrefillField:
        if master_value:
            return PurchasePrefillField(
                field_name=name, value=master_value, resolution="EXACT", source="SUPPLIER_MASTER"
            )
        return self._history_field(name, snapshots)

    @staticmethod
    def _history_field(name: str, snapshots: list[PurchaseFields]) -> PurchasePrefillField:
        values = tuple(
            dict.fromkeys(
                str(value)
                for item in snapshots
                if (value := getattr(item, name, None)) not in {None, ""}
            )
        )
        if len(values) == 1:
            return PurchasePrefillField(
                field_name=name,
                value=values[0],
                resolution="RECOMMENDED",
                source="PURCHASE_HISTORY",
                evidence_count=sum(
                    1 for item in snapshots if getattr(item, name, None) not in {None, ""}
                ),
            )
        if len(values) > 1:
            return PurchasePrefillField(
                field_name=name,
                value=None,
                resolution="AMBIGUOUS",
                source="PURCHASE_HISTORY",
                evidence_count=len(snapshots),
                alternatives=values,
            )
        return PurchasePrefillField(
            field_name=name, value=None, resolution="MISSING", source="PURCHASE_HISTORY"
        )


class PurchasePrefillNotificationService:
    """Build optional purchaser prefill content outside the notification gateway."""

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._prefill = PurchasePrefillService(backend)

    async def render(self, request: NotificationGatewayRequest) -> InteractionNotification | None:
        requirement_id = request.payload.get("requirement_id")
        if not isinstance(requirement_id, int):
            return None
        identity = PlatformIdentity.create(PlatformType.FEISHU, request.receiver_platform_user_id)
        user = await self._backend.get_current_user(identity=identity)
        result = await self._prefill.prepare(
            identity=identity, user=user, requirement_id=requirement_id
        )
        if result.status != "SUCCESS":
            return None
        return InteractionNotification(
            view=InteractionView(
                title="采购员预填推荐",
                subtitle="仅展示建议, 请打开正式卡片确认",
                elements=(
                    KeyValueSection(
                        fields=tuple(
                            KeyValueField(
                                label=item.field_name,
                                value=item.value
                                if item.value is not None
                                else "/".join(item.alternatives) or "待补充",
                            )
                            for item in result.fields
                        )
                    ),
                ),
                actions=(
                    ActionButton(
                        action_id="purchaser.open_requirement",
                        label="打开采购卡片",
                        value={"requirement_id": requirement_id},
                        style="primary",
                    ),
                ),
            )
        )


class PreparePurchasePrefillTool:
    name = "prepare_purchase_prefill"
    description = "Prepare purchaser fields using the supplier selected by the building manager."
    args_model = PreparePurchasePrefillArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._service = PurchasePrefillService(backend)

    async def execute(
        self, *, args: PreparePurchasePrefillArgs, context: AssistantToolContext
    ) -> PreparePurchasePrefillResult:
        resolved = await _active_user(self._backend, context, RoleCode.PURCHASER)
        if resolved is None:
            return PreparePurchasePrefillResult(
                status="PERMISSION_DENIED", user_message="当前用户不是有效采购员"
            )
        identity, user = resolved
        try:
            return await self._service.prepare(
                identity=identity, user=user, requirement_id=args.requirement_id
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return PreparePurchasePrefillResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )


class UpdatePurchaseExecutionDraftArgs(StrictArgs):
    requirement_id: int = Field(gt=0)
    supplier_tax_number: str | None = Field(default=None, max_length=50)
    bank_name: str | None = Field(default=None, max_length=200)
    bank_account: str | None = Field(default=None, max_length=255)
    registered_address: str | None = Field(default=None, max_length=500)
    contract_contact_info: str | None = Field(default=None, max_length=255)
    actual_unit_price: str | None = None
    tax_rate: str | None = None
    purchased_at: datetime | None = None
    purchase_remark: str | None = None
    update_supplier_profile: bool = False


class UpdatePurchaseExecutionDraftResult(AssistantToolResult):
    updated_fields: tuple[str, ...] = ()
    actual_total_price: str | None = None
    missing_fields: tuple[str, ...] = ()
    fields_complete: bool = False


class UpdatePurchaseExecutionDraftTool:
    name = "update_purchase_execution_draft"
    description = (
        "Save purchaser execution draft fields without starting or submitting procurement."
    )
    args_model = UpdatePurchaseExecutionDraftArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def execute(
        self, *, args: UpdatePurchaseExecutionDraftArgs, context: AssistantToolContext
    ) -> UpdatePurchaseExecutionDraftResult:
        resolved = await _active_user(self._backend, context, RoleCode.PURCHASER)
        if resolved is None:
            return UpdatePurchaseExecutionDraftResult(
                status="PERMISSION_DENIED", user_message="当前用户不是有效采购员"
            )
        identity, user = resolved
        try:
            detail = await self._backend.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            if detail.status is not RequirementStatus.PURCHASING:
                return UpdatePurchaseExecutionDraftResult(
                    status="INVALID_STATUS", user_message="只有采购中状态可以保存执行草稿"
                )
            if not _is_handler(detail, user):
                return UpdatePurchaseExecutionDraftResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是该采购单处理人"
                )
            supplier_id = (
                detail.review_fields.proposed_supplier_id if detail.review_fields else None
            )
            if supplier_id is None:
                return UpdatePurchaseExecutionDraftResult(
                    status="NOT_FOUND", user_message="楼长尚未确定供应商"
                )
            existing = detail.purchase_fields or PurchaseFields()
            raw = args.model_dump(exclude={"requirement_id"}, exclude_unset=True)
            unit_price = raw.get("actual_unit_price", existing.actual_unit_price)
            purchased_at = raw.get("purchased_at", existing.purchased_at)
            if unit_price is None or purchased_at is None:
                return UpdatePurchaseExecutionDraftResult(
                    status="NEED_MORE_INFORMATION", user_message="请补充实际单价和采购时间"
                )
            try:
                unit_decimal = Decimal(str(unit_price))
                quantity = Decimal(detail.applicant_fields.quantity or "0")
                tax_rate = raw.get("tax_rate", existing.tax_rate)
                tax_decimal = Decimal(str(tax_rate)) if tax_rate is not None else None
                if (
                    unit_decimal < 0
                    or quantity <= 0
                    or (
                        tax_decimal is not None
                        and not Decimal("0") <= tax_decimal <= Decimal("100")
                    )
                ):
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                return UpdatePurchaseExecutionDraftResult(
                    status="INVALID_ARGUMENTS", user_message="金额、数量或税率格式无效"
                )
            total = format(quantity * unit_decimal, "f")
            merged = {
                "supplier_id": supplier_id,
                "supplier_tax_number": raw.get("supplier_tax_number", existing.supplier_tax_number),
                "bank_name": raw.get("bank_name", existing.bank_name),
                "bank_account": raw.get("bank_account", existing.bank_account),
                "registered_address": raw.get("registered_address", existing.registered_address),
                "contract_contact_info": raw.get(
                    "contract_contact_info", existing.contract_contact_info
                ),
                "actual_unit_price": str(unit_price),
                "actual_total_price": total,
                "tax_rate": raw.get("tax_rate", existing.tax_rate),
                "purchased_at": purchased_at,
                "purchase_remark": raw.get("purchase_remark", existing.purchase_remark),
                "update_supplier_profile": args.update_supplier_profile,
            }
            saved = await self._backend.update_purchase_fields(
                identity=identity,
                requirement_id=args.requirement_id,
                expected_version=detail.version,
                fields=PurchaseFieldsPatch.model_validate(merged),
            )
            latest = await self._backend.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            return UpdatePurchaseExecutionDraftResult(
                status="SUCCESS",
                requirement_id=args.requirement_id,
                requirement_version=latest.version,
                updated_fields=tuple(raw),
                actual_total_price=total,
                missing_fields=saved.missing_fields,
                fields_complete=saved.fields_complete,
            )
        except ConcurrentModificationError:
            return UpdatePurchaseExecutionDraftResult(
                status="CONCURRENT_MODIFICATION", user_message="版本已变化, 请重新确认"
            )


class UpdateWarehouseReceiptDraftArgs(StrictArgs):
    requirement_id: int = Field(gt=0)
    received_quantity: str | None = None
    warehouse_location: str | None = Field(default=None, max_length=255)
    receipt_remark: str | None = None


class UpdateWarehouseReceiptDraftResult(AssistantToolResult):
    updated_fields: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    fields_complete: bool = False


class UpdateWarehouseReceiptDraftTool:
    name = "update_warehouse_receipt_draft"
    description = "Save warehouse receipt draft fields without completing the requirement."
    args_model = UpdateWarehouseReceiptDraftArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def execute(
        self, *, args: UpdateWarehouseReceiptDraftArgs, context: AssistantToolContext
    ) -> UpdateWarehouseReceiptDraftResult:
        resolved = await _active_user(self._backend, context, RoleCode.WAREHOUSE_MANAGER)
        if resolved is None:
            return UpdateWarehouseReceiptDraftResult(
                status="PERMISSION_DENIED", user_message="当前用户不是有效仓库管理员"
            )
        identity, user = resolved
        try:
            detail = await self._backend.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            if detail.status is not RequirementStatus.PENDING_WAREHOUSE:
                return UpdateWarehouseReceiptDraftResult(
                    status="INVALID_STATUS", user_message="当前状态不可保存入库草稿"
                )
            if not _is_handler(detail, user):
                return UpdateWarehouseReceiptDraftResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是该采购单处理人"
                )
            existing = detail.warehouse_fields
            quantity_text = args.received_quantity or (
                existing.received_quantity if existing else None
            )
            location = args.warehouse_location or (
                existing.warehouse_location if existing else None
            )
            if not quantity_text or not location:
                return UpdateWarehouseReceiptDraftResult(
                    status="NEED_MORE_INFORMATION", user_message="请补充实收数量和入库位置"
                )
            try:
                received = Decimal(quantity_text)
                requested = Decimal(detail.applicant_fields.quantity or "0")
            except InvalidOperation:
                return UpdateWarehouseReceiptDraftResult(
                    status="INVALID_ARGUMENTS", user_message="实收数量格式无效"
                )
            remark = (
                args.receipt_remark
                if "receipt_remark" in args.model_fields_set
                else existing.receipt_remark
                if existing
                else None
            )
            if received < requested and not remark:
                return UpdateWarehouseReceiptDraftResult(
                    status="NEED_MORE_INFORMATION", user_message="少收时必须填写入库备注"
                )
            raw = {
                "received_quantity": quantity_text,
                "warehouse_location": location,
                "receipt_remark": remark,
            }
            saved = await self._backend.update_warehouse_fields(
                identity=identity,
                requirement_id=args.requirement_id,
                expected_version=detail.version,
                fields=WarehouseFieldsPatch.model_validate(raw),
            )
            latest = await self._backend.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            return UpdateWarehouseReceiptDraftResult(
                status="SUCCESS",
                requirement_id=args.requirement_id,
                requirement_version=latest.version,
                updated_fields=tuple(
                    args.model_dump(exclude={"requirement_id"}, exclude_unset=True)
                ),
                missing_fields=saved.missing_fields,
                fields_complete=saved.fields_complete,
            )
        except ConcurrentModificationError:
            return UpdateWarehouseReceiptDraftResult(
                status="CONCURRENT_MODIFICATION", user_message="版本已变化, 请重新确认"
            )
