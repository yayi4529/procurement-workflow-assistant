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
from procurement_platform.domain.requirement import SupplierRecommendation
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
                current.model_dump(exclude={"conversation_id", "expires_in_seconds"})
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
            recommendations = await self._backend_client.recommend_suppliers(
                identity=identity, requirement_id=args.requirement_id, limit=args.limit
            )
            candidates = tuple(
                self._candidate(item) for item in recommendations.items[: args.limit]
            )
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

    @staticmethod
    def _candidate(item: SupplierRecommendation) -> SupplierRecommendationCandidate:
        return SupplierRecommendationCandidate(
            candidate_ref=f"supplier:{item.supplier_id}",
            supplier_id=item.supplier_id,
            supplier_name=item.supplier_name,
            historical_purchase_count=item.historical_purchase_count,
            last_purchase_at=item.last_purchase_at,
            blacklist_status=item.blacklist_status,
        )
