"""Building-manager supplier recommendation tool for the optional assistant."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult
from procurement_platform.domain.assistant_session import (
    AgentSessionStateUpdate,
    RecommendationReference,
)
from procurement_platform.domain.enums import PlatformType, RequirementStatus, RoleCode
from procurement_platform.domain.errors import (
    BackendApplicationError,
    BackendProtocolError,
    BackendTimeoutError,
    BackendUnavailableError,
    InvalidHandlerError,
    InvalidStatusError,
    PermissionDeniedError,
    SessionNotFoundError,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import PurchaseRecord
from procurement_platform.ports.backend_client import BackendClient


class RecommendSuppliersForRequirementArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: int = Field(gt=0)
    limit: int = Field(default=3, ge=1, le=3)


class SupplierRecommendationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_ref: str
    supplier_id: int
    supplier_name: str
    historical_purchase_count: int
    last_purchase_at: datetime
    blacklist_status: str


class RecommendSuppliersForRequirementResult(AssistantToolResult):
    model_config = ConfigDict(extra="forbid")

    candidates: tuple[SupplierRecommendationCandidate, ...] = ()


class SupplierRecommendationReferenceStore:
    """Persists non-sensitive supplier references in the backend session state."""

    def __init__(self, backend_client: BackendClient) -> None:
        self._backend_client = backend_client

    async def save(
        self,
        *,
        identity: PlatformIdentity,
        conversation_id: int,
        requirement_id: int,
        candidates: tuple[SupplierRecommendationCandidate, ...],
    ) -> str:
        references = tuple(
            RecommendationReference(
                reference_id=candidate.candidate_ref,
                kind="SUPPLIER_RECOMMENDATION",
                label=candidate.supplier_name,
            )
            for candidate in candidates
        )
        try:
            current = await self._backend_client.get_agent_state(
                identity=identity, conversation_id=conversation_id
            )
            state = AgentSessionStateUpdate.model_validate(
                current.model_dump(
                    exclude={"conversation_id", "expires_in_seconds", "restored_from_snapshot"}
                )
            )
        except SessionNotFoundError:
            state = AgentSessionStateUpdate()
        await self._backend_client.update_agent_state(
            identity=identity,
            conversation_id=conversation_id,
            state=state.model_copy(
                update={
                    "purchase_request_id": requirement_id,
                    "last_recommendations": references,
                    "focused_role": RoleCode.BUILDING_MANAGER,
                }
            ),
        )
        return f"supplier-recommendations:{conversation_id}:{requirement_id}"


class RecommendSuppliersForRequirementTool:
    name = "recommend_suppliers_for_requirement"
    description = "Recommend eligible suppliers for a building manager's pending review."
    args_model = RecommendSuppliersForRequirementArgs

    def __init__(self, backend_client: BackendClient) -> None:
        self._backend_client = backend_client
        self._reference_store = SupplierRecommendationReferenceStore(backend_client)

    async def execute(
        self,
        *,
        args: RecommendSuppliersForRequirementArgs,
        context: AssistantToolContext,
    ) -> RecommendSuppliersForRequirementResult:
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        try:
            current_user = await self._backend_client.get_current_user(identity=identity)
            if current_user.status != "ACTIVE" or not any(
                role.role_code is RoleCode.BUILDING_MANAGER for role in current_user.roles
            ):
                return RecommendSuppliersForRequirementResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是有效楼长"
                )
            detail = await self._backend_client.get_requirement(
                identity=identity, requirement_id=args.requirement_id
            )
            if detail.status is not RequirementStatus.PENDING_REVIEW:
                return RecommendSuppliersForRequirementResult(
                    status="INVALID_STATUS", user_message="当前状态不可推荐供应商"
                )
            if detail.building.building_id not in {
                building.building_id for building in current_user.buildings
            } or (
                detail.current_handler is None
                or detail.current_handler.employee_id != current_user.employee_id
            ):
                return RecommendSuppliersForRequirementResult(
                    status="PERMISSION_DENIED", user_message="当前用户不是该采购单处理人"
                )
            records: list[PurchaseRecord] = []
            page = 1
            while True:
                history = await self._backend_client.list_purchase_records(
                    identity=identity,
                    device_name=detail.applicant_fields.device_name,
                    brand=detail.applicant_fields.brand,
                    page=page,
                    page_size=100,
                )
                records.extend(history.items)
                if len(records) >= history.total:
                    break
                page += 1

            grouped: dict[int, list[datetime]] = {}
            supplier_names: dict[int, str] = {}
            for record in records:
                if (
                    record.status
                    not in {RequirementStatus.PENDING_WAREHOUSE, RequirementStatus.COMPLETED}
                    or record.purchased_at is None
                    or record.supplier_id is None
                    or record.supplier_name is None
                ):
                    continue
                grouped.setdefault(record.supplier_id, []).append(record.purchased_at)
                supplier_names[record.supplier_id] = record.supplier_name

            matched: list[SupplierRecommendationCandidate] = []
            for supplier_id, purchase_dates in grouped.items():
                supplier = await self._backend_client.get_supplier(
                    identity=identity, supplier_id=supplier_id
                )
                if supplier.blacklist and supplier.blacklist.active:
                    continue
                matched.append(
                    SupplierRecommendationCandidate(
                        candidate_ref=f"supplier:{supplier_id}",
                        supplier_id=supplier_id,
                        supplier_name=supplier.supplier_name or supplier_names[supplier_id],
                        historical_purchase_count=len(purchase_dates),
                        last_purchase_at=max(purchase_dates),
                        blacklist_status="NORMAL",
                    )
                )
            matched.sort(
                key=lambda item: (item.historical_purchase_count, item.last_purchase_at),
                reverse=True,
            )
            candidates = tuple(matched[: args.limit])
            candidate_set_id = await self._reference_store.save(
                identity=identity,
                conversation_id=context.conversation_id,
                requirement_id=args.requirement_id,
                candidates=candidates,
            )
            return RecommendSuppliersForRequirementResult(
                status="SUCCESS",
                requirement_id=detail.requirement_id,
                requirement_version=detail.version,
                candidate_set_id=candidate_set_id,
                candidates=candidates,
                user_message=("未找到可推荐供应商" if not candidates else None),
            )
        except (PermissionDeniedError, InvalidHandlerError):
            return RecommendSuppliersForRequirementResult(
                status="PERMISSION_DENIED", user_message="无权查询该采购单"
            )
        except InvalidStatusError:
            return RecommendSuppliersForRequirementResult(
                status="INVALID_STATUS", user_message="当前状态不可推荐供应商"
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return RecommendSuppliersForRequirementResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )
        except BackendApplicationError:
            return RecommendSuppliersForRequirementResult(
                status="BACKEND_UNAVAILABLE", user_message="供应商推荐暂时不可用"
            )
