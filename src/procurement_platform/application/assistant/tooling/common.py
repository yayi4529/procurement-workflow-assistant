"""Task 9 domain tools shared by the optional conversational assistant."""

from datetime import datetime, timedelta
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    InvalidHandlerError,
    PermissionDeniedError,
    RequirementNotFoundError,
    SessionNotFoundError,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import (
    PurchaseRecord,
    RequirementDetail,
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


class _UnsetType(Enum):
    TOKEN = "UNSET"


UNSET = _UnsetType.TOKEN


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DraftUpdateResultBase(AssistantToolResult):
    """Common action observation returned by every role's draft update tool."""

    updated_fields: tuple[str, ...] = ()
    updated_values: dict[str, str | None] = Field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()
    next_missing_field: str | None = None
    fields_complete: bool = False

    @model_validator(mode="after")
    def successful_progress_is_consistent(self) -> "DraftUpdateResultBase":
        if self.status != "SUCCESS":
            if self.updated_fields or self.updated_values:
                raise ValueError("failed draft updates cannot report updated fields")
            return self
        if self.fields_complete:
            if self.missing_fields or self.next_missing_field is not None:
                raise ValueError("complete draft updates cannot have missing fields")
        elif not self.missing_fields or self.next_missing_field not in self.missing_fields:
            raise ValueError("incomplete draft updates require a next missing field")
        return self


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
        requirement_id: int | _UnsetType | None = UNSET,
        references: tuple[RecommendationReference, ...] | _UnsetType = UNSET,
        focused_role: RoleCode | _UnsetType | None = UNSET,
        focused_field: str | _UnsetType | None = UNSET,
        missing_fields: tuple[str, ...] | None = None,
        pending_field: str | _UnsetType | None = UNSET,
        collected_data: dict[str, JsonValue] | None = None,
        awaiting_confirmation: bool | _UnsetType = UNSET,
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
        changes: dict[str, object] = {
            "collected_data": merged_data,
            "missing_fields": missing_fields
            if missing_fields is not None
            else update.missing_fields,
        }
        if requirement_id is not UNSET:
            changes["purchase_request_id"] = requirement_id
        if pending_field is not UNSET:
            changes["pending_field"] = pending_field
        if focused_role is not UNSET:
            changes["focused_role"] = focused_role
        if focused_field is not UNSET:
            changes["focused_field"] = focused_field
        if awaiting_confirmation is not UNSET:
            changes["awaiting_confirmation"] = awaiting_confirmation
        if clear_recommendations:
            changes["last_recommendations"] = ()
        elif references is not UNSET:
            changes["last_recommendations"] = references
        await self._backend.update_agent_state(
            identity=identity,
            conversation_id=context.conversation_id,
            state=update.model_copy(update=changes),
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
    requirement_no: str | None = Field(default=None, min_length=1, max_length=50)
    time_expression: str | None = Field(default=None, max_length=50)
    time_field: TimeField = "CREATED_AT"
    device_name: str | None = Field(default=None, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=150)
    status: RequirementStatus | None = None
    result_limit: int = Field(default=10, ge=1, le=20)

    @model_validator(mode="after")
    def validate_operation(self) -> "QueryPurchaseRequestsArgs":
        if (
            self.operation != "SEARCH"
            and self.requirement_id is None
            and self.requirement_no is None
        ):
            raise ValueError("requirement_id or requirement_no is required for detail or timeline")
        return self


class QueryPurchaseRequestsResult(AssistantToolResult):
    records: tuple[PurchaseRequestCandidate, ...] = ()
    total_count: int | None = Field(default=None, ge=0)
    timeline: tuple[str, ...] = ()
    requirement_no: str | None = None
    status_value: RequirementStatus | None = None
    current_handler_name: str | None = None
    missing_fields: tuple[str, ...] = ()


class PurchaseRequestQueryService:
    """Deterministic requirement reads shared by V2 capabilities and the legacy wrapper."""

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._temporal = TemporalRangeResolver()
        self._session = SessionReferenceStore(backend)

    async def search(
        self, *, args: QueryPurchaseRequestsArgs, context: AssistantToolContext
    ) -> QueryPurchaseRequestsResult:
        identity = _identity(context)
        try:
            await self._backend.get_current_user(identity=identity)
            window = (
                self._temporal.resolve(args.time_expression, now=context.current_time)
                if args.time_expression
                else None
            )
            page = await self._backend.list_purchase_records(
                identity=identity,
                requirement_no=args.requirement_no,
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
                    status="NOT_FOUND",
                    user_message="未找到符合条件的采购单",
                    total_count=page.total if window is None else None,
                )
            if len(matched) == 1:
                return self._detail(
                    await self._backend.get_requirement(
                        identity=identity, requirement_id=matched[0][0].requirement_id
                    )
                ).model_copy(update={"total_count": page.total if window is None else None})
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
                status="MULTIPLE_MATCHES",
                candidate_set_id=candidate_set,
                records=candidates,
                total_count=page.total if window is None else None,
            )
        except ValueError as exc:
            return QueryPurchaseRequestsResult(status="INVALID_ARGUMENTS", user_message=str(exc))
        except (PermissionDeniedError, InvalidHandlerError):
            return QueryPurchaseRequestsResult(
                status="PERMISSION_DENIED", user_message="无权查看该采购单"
            )
        except RequirementNotFoundError:
            return QueryPurchaseRequestsResult(
                status="NOT_FOUND", user_message="未找到该采购单, 请核对完整采购单编号"
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return QueryPurchaseRequestsResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )

    async def get_detail(
        self, *, args: QueryPurchaseRequestsArgs, context: AssistantToolContext
    ) -> QueryPurchaseRequestsResult:
        identity = _identity(context)
        try:
            await self._backend.get_current_user(identity=identity)
            requirement_id = await self._resolve_requirement_id(identity, args)
            return self._detail(
                await self._backend.get_requirement(
                    identity=identity, requirement_id=requirement_id
                )
            )
        except (PermissionDeniedError, InvalidHandlerError):
            return QueryPurchaseRequestsResult(
                status="PERMISSION_DENIED", user_message="无权查看该采购单"
            )
        except RequirementNotFoundError:
            return QueryPurchaseRequestsResult(
                status="NOT_FOUND", user_message="未找到该采购单, 请核对完整采购单编号"
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return QueryPurchaseRequestsResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )

    async def get_timeline(
        self, *, args: QueryPurchaseRequestsArgs, context: AssistantToolContext
    ) -> QueryPurchaseRequestsResult:
        identity = _identity(context)
        try:
            await self._backend.get_current_user(identity=identity)
            requirement_id = await self._resolve_requirement_id(identity, args)
            timeline = await self._backend.get_requirement_timeline(
                identity=identity, requirement_id=requirement_id
            )
            return QueryPurchaseRequestsResult(
                status="SUCCESS",
                requirement_id=requirement_id,
                requirement_no=args.requirement_no,
                timeline=tuple(
                    (
                        f"{item.operated_at.isoformat()} {item.action_type}: "
                        f"{item.operation_summary or item.to_status or ''}"
                    )
                    for item in timeline.items
                ),
            )
        except (PermissionDeniedError, InvalidHandlerError):
            return QueryPurchaseRequestsResult(
                status="PERMISSION_DENIED", user_message="无权查看该采购单"
            )
        except RequirementNotFoundError:
            return QueryPurchaseRequestsResult(
                status="NOT_FOUND", user_message="未找到该采购单, 请核对完整采购单编号"
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return QueryPurchaseRequestsResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )

    async def _resolve_requirement_id(
        self, identity: PlatformIdentity, args: QueryPurchaseRequestsArgs
    ) -> int:
        if args.requirement_no:
            page = await self._backend.list_purchase_records(
                identity=identity,
                requirement_no=args.requirement_no,
                page=1,
                page_size=20,
            )
            exact = tuple(item for item in page.items if item.requirement_no == args.requirement_no)
            if len(exact) != 1:
                raise RequirementNotFoundError(
                    "REQUIREMENT_NOT_FOUND", "采购申请不存在或编号不唯一"
                )
            return exact[0].requirement_id
        assert args.requirement_id is not None
        return args.requirement_id

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
        if direct is not None and direct.tzinfo is None:
            direct = direct.replace(tzinfo=window.start.tzinfo)
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


class QueryPurchaseRequestsTool:
    """Legacy operation-based wrapper; never registered for LLM use."""

    name = "query_purchase_requests"
    side_effect = "READ"
    description = "Query visible purchase requests, details, current handler, or timeline."
    args_model = QueryPurchaseRequestsArgs

    def __init__(self, backend: BackendClient) -> None:
        self._service = PurchaseRequestQueryService(backend)

    async def execute(
        self, *, args: QueryPurchaseRequestsArgs, context: AssistantToolContext
    ) -> QueryPurchaseRequestsResult:
        if args.operation == "GET_DETAIL":
            return await self._service.get_detail(args=args, context=context)
        if args.operation == "GET_TIMELINE":
            return await self._service.get_timeline(args=args, context=context)
        return await self._service.search(args=args, context=context)
