"""Evidence-first procurement intelligence capabilities.

All ranking is deterministic and uses only data returned by ``BackendClient``.
The capabilities are advisory READ operations and never advance workflow state.
"""

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field

from procurement_platform.application.assistant.tooling.common import (
    SessionReferenceStore,
    StrictArgs,
    _identity,
)
from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult
from procurement_platform.domain.assistant_session import JsonValue, RecommendationReference
from procurement_platform.domain.enums import RequirementStatus
from procurement_platform.domain.errors import (
    BackendProtocolError,
    BackendTimeoutError,
    BackendUnavailableError,
    SessionNotFoundError,
)
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.domain.requirement import PurchaseRecord
from procurement_platform.ports.backend_client import BackendClient


class MatchConfidence(StrEnum):
    EXACT = "EXACT"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    FALLBACK = "FALLBACK"


class ProcurementNeedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_ref: str
    device_profession: str | None = None
    device_name: str
    category: str | None = None
    brand: str | None = None
    model: str | None = None
    product_id: int | None = None
    confidence: MatchConfidence
    evidence: tuple[str, ...]


class DiagnoseProcurementNeedArgs(StrictArgs):
    symptom_text: str = Field(min_length=1, max_length=1000)
    building_id: int | None = Field(default=None, gt=0)
    device_hint: str | None = Field(default=None, max_length=200)
    profession_hint: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=5, ge=1, le=10)


class DiagnoseProcurementNeedResult(AssistantToolResult):
    normalized_symptom: str
    candidates: tuple[ProcurementNeedCandidate, ...] = ()
    clarification_needed: bool
    clarification_hint: str | None = None
    insufficient_data: tuple[str, ...] = ()
    ranking_version: str = "procurement_need_v1"


class DiagnoseProcurementNeedCapability:
    name = "diagnose_procurement_need"
    side_effect = "READ"
    description = (
        "Diagnose a procurement need from a reported symptom using backend product and "
        "history evidence. Returns advisory candidates and uncertainty; it never saves a draft."
    )
    args_model = DiagnoseProcurementNeedArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._references = SessionReferenceStore(backend)

    async def execute(
        self, *, args: DiagnoseProcurementNeedArgs, context: AssistantToolContext
    ) -> DiagnoseProcurementNeedResult:
        symptom = " ".join(args.symptom_text.split())
        identity = _identity(context)
        try:
            await self._backend.get_current_user(identity=identity)
            device_name = args.device_hint or symptom
            recommendations = await self._backend.recommend_products(
                identity=identity,
                device_name=device_name,
                device_profession=args.profession_hint,
                keyword=symptom,
                limit=args.limit,
            )
            candidates = tuple(
                ProcurementNeedCandidate(
                    candidate_ref=self._product_ref(item.brand, item.model),
                    device_profession=args.profession_hint,
                    device_name=device_name,
                    brand=item.brand,
                    model=item.model,
                    confidence=(
                        MatchConfidence.HIGH
                        if args.device_hint and item.historical_count > 0
                        else MatchConfidence.MEDIUM
                        if item.historical_count > 0
                        else MatchConfidence.LOW
                    ),
                    evidence=(
                        f"后端历史采购次数: {item.historical_count}",
                        f"最近采购时间: {item.last_purchased_at.isoformat()}",
                    ),
                )
                for item in recommendations.items[: args.limit]
            )
            await self._save_product_references(identity, context, candidates)
            return DiagnoseProcurementNeedResult(
                status="SUCCESS" if candidates else "NOT_FOUND",
                normalized_symptom=symptom,
                candidates=candidates,
                clarification_needed=len(candidates) != 1 or not args.device_hint,
                clarification_hint=(
                    "请确认具体设备或部件" if not candidates or not args.device_hint else None
                ),
                insufficient_data=("系统没有故障原因和设备健康数据",),
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return DiagnoseProcurementNeedResult(
                status="BACKEND_UNAVAILABLE",
                user_message="采购后端暂时不可用",
                normalized_symptom=symptom,
                clarification_needed=True,
                clarification_hint="请稍后重试",
            )

    async def _save_product_references(
        self,
        identity: PlatformIdentity,
        context: AssistantToolContext,
        candidates: tuple[ProcurementNeedCandidate, ...],
    ) -> None:
        if not candidates:
            return
        data: dict[str, JsonValue] = {}
        refs = []
        for item in candidates:
            refs.append(
                RecommendationReference(
                    reference_id=item.candidate_ref,
                    kind="PRODUCT_RECOMMENDATION",
                    label=f"{item.brand or ''} {item.model or ''}".strip(),
                )
            )
            data[f"product_candidate:{item.candidate_ref}:brand"] = item.brand
            data[f"product_candidate:{item.candidate_ref}:model"] = item.model
            data[f"product_candidate:{item.candidate_ref}:count"] = int(
                item.evidence[0].rsplit(":", 1)[1]
            )
        await self._references.save(
            identity=identity,
            context=context,
            references=tuple(refs),
            collected_data=data,
            awaiting_confirmation=True,
        )

    @staticmethod
    def _product_ref(brand: str | None, model: str | None) -> str:
        digest = sha256(f"{brand}|{model}".encode()).hexdigest()[:12]
        return f"product:{digest}"


class SimilarPurchaseCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_ref: str
    requirement_id: int
    requirement_no: str
    building_id: int | None = None
    device_profession: str | None = None
    device_name: str | None = None
    brand: str | None = None
    model: str | None = None
    quantity: str | None = None
    unit: str | None = None
    completed_at: datetime | None = None
    similarity_score: float
    match_reasons: tuple[str, ...]


class FindSimilarPurchasesArgs(StrictArgs):
    building_id: int | None = Field(default=None, gt=0)
    device_profession: str | None = Field(default=None, max_length=100)
    device_name: str | None = Field(default=None, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=150)
    keyword: str | None = Field(default=None, max_length=200)
    time_range: str | None = Field(default=None, max_length=50)
    limit: int = Field(default=5, ge=1, le=20)


class FindSimilarPurchasesResult(AssistantToolResult):
    candidates: tuple[SimilarPurchaseCandidate, ...] = ()
    insufficient_data: tuple[str, ...] = ()
    ranking_version: str = "similar_purchase_v1"


class HistoricalPurchaseRanker:
    """Stable structured ranking: model 40, device 25, building 20, recency 15."""

    @staticmethod
    def score(
        record: PurchaseRecord,
        *,
        building_match: bool,
        device_name: str | None,
        brand: str | None,
        model: str | None,
        now: datetime,
    ) -> tuple[float, tuple[str, ...]]:
        score = 0.0
        reasons: list[str] = []
        if model and record.model and model.casefold() == record.model.casefold():
            score += 0.40
            reasons.append("型号完全匹配")
        if brand and record.brand and brand.casefold() == record.brand.casefold():
            score += 0.10
            reasons.append("品牌匹配")
        if (
            device_name
            and record.device_name
            and device_name.casefold() in record.device_name.casefold()
        ):
            score += 0.25
            reasons.append("设备名称匹配")
        if building_match:
            score += 0.20
            reasons.append("楼宇匹配")
        at = record.completed_at or record.purchased_at or record.created_at
        normalized_now = now if now.tzinfo else now.replace(tzinfo=UTC)
        normalized_at = at if at.tzinfo else at.replace(tzinfo=UTC)
        age_days = max(0, (normalized_now - normalized_at).days)
        recency = max(0.0, 0.15 * (1 - min(age_days, 730) / 730))
        score += recency
        if recency:
            reasons.append("近期采购")
        return round(score, 4), tuple(reasons)


class FindSimilarPurchasesCapability:
    name = "find_similar_purchases"
    side_effect = "READ"
    description = (
        "Find and rank authoritative historical purchases using structured device, building, "
        "model and recency evidence. Read-only; sensitive or workflow fields are not reused."
    )
    args_model = FindSimilarPurchasesArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend
        self._references = SessionReferenceStore(backend)

    async def execute(
        self, *, args: FindSimilarPurchasesArgs, context: AssistantToolContext
    ) -> FindSimilarPurchasesResult:
        identity = _identity(context)
        try:
            await self._backend.get_current_user(identity=identity)
            page = await self._backend.list_purchase_records(
                identity=identity,
                device_name=args.device_name or args.keyword,
                brand=args.brand,
                model=args.model,
                page=1,
                page_size=100,
            )
            ranked: list[SimilarPurchaseCandidate] = []
            for record in page.items:
                if record.status is not RequirementStatus.COMPLETED:
                    continue
                detail = await self._backend.get_requirement(
                    identity=identity, requirement_id=record.requirement_id
                )
                if (
                    args.device_profession
                    and (detail.applicant_fields.device_profession or "").casefold()
                    != args.device_profession.casefold()
                ):
                    continue
                score, reasons = HistoricalPurchaseRanker.score(
                    record,
                    building_match=(
                        args.building_id is not None
                        and detail.building.building_id == args.building_id
                    ),
                    device_name=args.device_name or args.keyword,
                    brand=args.brand,
                    model=args.model,
                    now=context.current_time,
                )
                ranked.append(
                    SimilarPurchaseCandidate(
                        candidate_ref=f"purchase:{record.requirement_id}",
                        requirement_id=record.requirement_id,
                        requirement_no=record.requirement_no,
                        building_id=detail.building.building_id,
                        device_profession=detail.applicant_fields.device_profession,
                        device_name=record.device_name,
                        brand=record.brand,
                        model=record.model,
                        quantity=record.quantity,
                        unit=record.unit,
                        completed_at=record.completed_at,
                        similarity_score=score,
                        match_reasons=reasons,
                    )
                )
            ranked.sort(
                key=lambda item: (
                    -item.similarity_score,
                    -(item.completed_at or datetime.min.replace(tzinfo=UTC)).timestamp(),
                    item.requirement_id,
                )
            )
            candidates = tuple(ranked[: args.limit])
            if candidates:
                await self._references.save(
                    identity=identity,
                    context=context,
                    references=tuple(
                        RecommendationReference(
                            reference_id=item.candidate_ref,
                            kind="SIMILAR_PURCHASE",
                            label=f"{item.requirement_no} {item.device_name or ''}".strip(),
                        )
                        for item in candidates
                    ),
                    awaiting_confirmation=len(candidates) > 1,
                )
            return FindSimilarPurchasesResult(
                status="SUCCESS" if candidates else "NOT_FOUND",
                candidates=candidates,
                insufficient_data=("历史数据不包含质量、故障率和交期",),
            )
        except (BackendUnavailableError, BackendTimeoutError, BackendProtocolError):
            return FindSimilarPurchasesResult(
                status="BACKEND_UNAVAILABLE", user_message="采购后端暂时不可用"
            )


class CompareProductsArgs(StrictArgs):
    candidate_refs: tuple[str, ...] = Field(min_length=2, max_length=10)
    requirement_id: int | None = Field(default=None, gt=0)
    comparison_focus: tuple[str, ...] | None = None


class ProductComparisonItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_ref: str
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    evidence: tuple[str, ...]
    fit_score: float | None


class CompareProductsResult(AssistantToolResult):
    items: tuple[ProductComparisonItem, ...] = ()
    recommended_ref: str | None = None
    recommendation_reason: tuple[str, ...] = ()
    insufficient_data: tuple[str, ...] = ()
    invalid_refs: tuple[str, ...] = ()
    ranking_version: str = "product_compare_v1"


class CompareProductsCapability:
    name = "compare_products"
    side_effect = "READ"
    description = (
        "Compare referenced product candidates using persisted backend evidence. Read-only; "
        "missing quality, delivery or price data is reported rather than inferred."
    )
    args_model = CompareProductsArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def execute(
        self, *, args: CompareProductsArgs, context: AssistantToolContext
    ) -> CompareProductsResult:
        identity = _identity(context)
        try:
            state = await self._backend.get_agent_state(
                identity=identity, conversation_id=context.conversation_id
            )
        except SessionNotFoundError:
            return CompareProductsResult(
                status="INVALID_ARGUMENTS",
                user_message="产品候选引用不存在或已过期",
                invalid_refs=args.candidate_refs,
            )
        refs = {
            item.reference_id
            for item in state.last_recommendations
            if item.kind == "PRODUCT_RECOMMENDATION"
        }
        invalid = tuple(ref for ref in args.candidate_refs if ref not in refs)
        items: list[ProductComparisonItem] = []
        for ref in args.candidate_refs:
            if ref not in refs:
                continue
            count = state.collected_data.get(f"product_candidate:{ref}:count")
            historical_count = count if isinstance(count, int) else None
            evidence = (
                (f"后端历史采购次数: {historical_count}",) if historical_count is not None else ()
            )
            items.append(
                ProductComparisonItem(
                    candidate_ref=ref,
                    strengths=("有历史采购记录",) if historical_count else (),
                    weaknesses=(),
                    evidence=evidence,
                    fit_score=float(historical_count) if historical_count is not None else None,
                )
            )
        eligible = [item for item in items if item.fit_score is not None]
        eligible.sort(key=lambda item: (-float(item.fit_score or 0), item.candidate_ref))
        recommended = eligible[0].candidate_ref if eligible else None
        return CompareProductsResult(
            status="SUCCESS" if items else "INVALID_ARGUMENTS",
            items=tuple(items),
            recommended_ref=recommended,
            recommendation_reason=("历史采购次数最高",) if recommended else (),
            insufficient_data=("系统没有质量、故障率、交期和实时价格数据",),
            invalid_refs=invalid,
        )


class CompareSuppliersArgs(StrictArgs):
    supplier_refs: tuple[str, ...] = Field(min_length=2, max_length=10)
    requirement_id: int | None = Field(default=None, gt=0)
    comparison_focus: tuple[str, ...] | None = None


class SupplierComparisonItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    supplier_ref: str
    strengths: tuple[str, ...]
    risks: tuple[str, ...]
    evidence: tuple[str, ...]
    fit_score: float | None
    blocked: bool


class CompareSuppliersResult(AssistantToolResult):
    items: tuple[SupplierComparisonItem, ...] = ()
    recommended_ref: str | None = None
    recommendation_reason: tuple[str, ...] = ()
    blocked_refs: tuple[str, ...] = ()
    insufficient_data: tuple[str, ...] = ()
    invalid_refs: tuple[str, ...] = ()
    ranking_version: str = "supplier_compare_v1"


class CompareSuppliersCapability:
    name = "compare_suppliers"
    side_effect = "READ"
    description = (
        "Compare referenced suppliers using current authoritative master data, blacklist "
        "status and visible purchase history. Read-only; blacklisted suppliers are blocked."
    )
    args_model = CompareSuppliersArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def execute(
        self, *, args: CompareSuppliersArgs, context: AssistantToolContext
    ) -> CompareSuppliersResult:
        identity = _identity(context)
        try:
            state = await self._backend.get_agent_state(
                identity=identity, conversation_id=context.conversation_id
            )
        except SessionNotFoundError:
            return CompareSuppliersResult(
                status="INVALID_ARGUMENTS",
                user_message="供应商候选引用不存在或已过期",
                invalid_refs=args.supplier_refs,
            )
        valid = {
            item.reference_id
            for item in state.last_recommendations
            if item.kind == "SUPPLIER_RECOMMENDATION"
        }
        invalid = tuple(ref for ref in args.supplier_refs if ref not in valid)
        items: list[SupplierComparisonItem] = []
        for ref in args.supplier_refs:
            if ref not in valid:
                continue
            try:
                supplier_id = int(ref.rsplit(":", 1)[1])
            except (IndexError, ValueError):
                invalid += (ref,)
                continue
            supplier = await self._backend.get_supplier(identity=identity, supplier_id=supplier_id)
            history = await self._backend.list_purchase_records(
                identity=identity, supplier_id=supplier_id, page=1, page_size=100
            )
            blocked = bool(supplier.blacklist and supplier.blacklist.active)
            count = len(history.items)
            items.append(
                SupplierComparisonItem(
                    supplier_ref=ref,
                    strengths=(f"可见历史采购 {count} 次",) if count else (),
                    risks=("供应商当前在黑名单中",) if blocked else (),
                    evidence=(
                        f"后端供应商主数据 ID: {supplier.supplier_id}",
                        f"可见历史采购次数: {count}",
                        f"黑名单状态: {'BLOCKED' if blocked else 'NORMAL'}",
                    ),
                    fit_score=None if blocked else float(count),
                    blocked=blocked,
                )
            )
        eligible = [item for item in items if not item.blocked]
        eligible.sort(key=lambda item: (-float(item.fit_score or 0), item.supplier_ref))
        recommended = eligible[0].supplier_ref if eligible else None
        blocked_refs = tuple(item.supplier_ref for item in items if item.blocked)
        return CompareSuppliersResult(
            status="SUCCESS" if items else "INVALID_ARGUMENTS",
            items=tuple(items),
            recommended_ref=recommended,
            recommendation_reason=("可见历史合作次数最高且不在黑名单",) if recommended else (),
            blocked_refs=blocked_refs,
            insufficient_data=("系统没有交期、服务质量和实时报价数据",),
            invalid_refs=invalid,
        )
