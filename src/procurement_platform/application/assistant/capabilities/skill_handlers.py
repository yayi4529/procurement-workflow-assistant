# ruff: noqa: RUF001

import asyncio
import json

from pydantic import BaseModel, ConfigDict, Field

from procurement_platform.application.assistant.tooling.common import StrictArgs
from procurement_platform.domain.analytics import AnalyticsCatalog, AnalyticsQueryResult
from procurement_platform.domain.assistant import (
    AssistantMessage,
    AssistantToolContext,
    AssistantToolResult,
)
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.errors import BackendApplicationError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.ports.backend_client import BackendClient
from procurement_platform.ports.llm_client import LlmClient


class AnalyticsEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result: AnalyticsQueryResult
    metric_definition: str
    attempts: int


class AnalyzeProcurementArgs(StrictArgs):
    question: str = Field(min_length=1, max_length=1000)
    include_synthetic: bool | None = None


class AnalyzeProcurementResult(AssistantToolResult):
    evidence: AnalyticsEvidence | None = None


class _SqlPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str = Field(min_length=1, max_length=20_000)
    metric_definition: str = Field(min_length=1, max_length=1000)


class ProcurementAnalyticsHandler:
    """One read-only skill operation wrapping catalog, SQL planning and one correction."""

    name = "analyze_procurement"
    side_effect = "READ"
    description = (
        "Analyze governed procurement facts for counts, rankings, trends, prices and delivery "
        "metrics. Internally reads the schema, plans safe aggregate SQL and corrects it at most "
        "once. Returns evidence and never changes procurement state."
    )
    args_model = AnalyzeProcurementArgs

    def __init__(self, backend: BackendClient, llm: LlmClient) -> None:
        self._backend = backend
        self._llm = llm

    async def execute(
        self, *, args: AnalyzeProcurementArgs, context: AssistantToolContext
    ) -> AnalyzeProcurementResult:
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        try:
            catalog = await self._backend.get_analytics_catalog(identity=identity)
        except BackendApplicationError as exc:
            return AnalyzeProcurementResult(
                status="PERMISSION_DENIED"
                if exc.error_code == "PERMISSION_DENIED"
                else "BACKEND_UNAVAILABLE",
                user_message=exc.user_message,
            )
        error: str | None = None
        for attempt in (1, 2):
            plan = await self._plan(args.question, catalog, previous_error=error)
            if plan is None:
                return AnalyzeProcurementResult(
                    status="INVALID_ARGUMENTS", user_message="无法生成有效的分析 SQL"
                )
            try:
                result = await self._backend.run_analytics_query(
                    identity=identity,
                    question=args.question,
                    sql=plan.sql,
                    include_synthetic=args.include_synthetic,
                )
                return AnalyzeProcurementResult(
                    status="SUCCESS",
                    evidence=AnalyticsEvidence(
                        result=result,
                        metric_definition=plan.metric_definition,
                        attempts=attempt,
                    ),
                )
            except BackendApplicationError as exc:
                error = exc.user_message
                if exc.error_code in {"PERMISSION_DENIED", "ANALYTICS_DISABLED"}:
                    return AnalyzeProcurementResult(
                        status="PERMISSION_DENIED"
                        if exc.error_code == "PERMISSION_DENIED"
                        else "BACKEND_UNAVAILABLE",
                        user_message=exc.user_message,
                    )
        return AnalyzeProcurementResult(
            status="INVALID_ARGUMENTS",
            user_message=f"分析 SQL 修正一次后仍未通过: {error or '未知校验错误'}",
        )

    async def _plan(
        self, question: str, catalog: AnalyticsCatalog, *, previous_error: str | None
    ) -> _SqlPlan | None:
        correction = f"\n上一次 SQL 的真实错误: {previous_error}" if previous_error else ""
        messages = (
            AssistantMessage(
                role="system",
                content=(
                    "你是只读采购分析 SQL 规划器。只输出 JSON: "
                    '{"sql":"...","metric_definition":"..."}。'
                    "仅使用给定视图和字段，MySQL 方言，统计必须在 SQL 中聚合，不使用原始业务表。"
                    f"\n语义目录:\n{catalog.model_dump_json()}"
                    f"{correction}"
                ),
            ),
            AssistantMessage(role="user", content=question),
        )
        try:
            turn = await self._llm.complete(messages=messages, tools=())
            if turn.tool_calls or turn.content is None:
                return None
            return _SqlPlan.model_validate(json.loads(turn.content))
        except Exception:
            return None


class SupplierEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    supplier_id: int
    supplier_name: str
    purchase_count: int
    purchase_amount: float | int | str | None
    average_delivery_days: float | int | str | None
    eligible: bool
    verification_status: str


class SupplierRecommendationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    analytics: AnalyticsEvidence
    candidates: tuple[SupplierEvidenceItem, ...]
    excluded_count: int


class RecommendSuppliersWithEvidenceArgs(StrictArgs):
    item_name: str | None = Field(default=None, max_length=200)
    top_k: int = Field(default=10, ge=1, le=10)
    include_synthetic: bool | None = None


class RecommendSuppliersWithEvidenceResult(AssistantToolResult):
    evidence: SupplierRecommendationEvidence | None = None


class SupplierRecommendationHandler:
    name = "recommend_suppliers_with_evidence"
    side_effect = "READ"
    description = (
        "Rank suppliers using governed purchase count, amount and delivery evidence, then verify "
        "supplier eligibility and blacklist state internally. Read-only and limited to ten."
    )
    args_model = RecommendSuppliersWithEvidenceArgs

    def __init__(self, backend: BackendClient, analytics: ProcurementAnalyticsHandler) -> None:
        self._backend = backend
        self._analytics = analytics

    async def execute(
        self, *, args: RecommendSuppliersWithEvidenceArgs, context: AssistantToolContext
    ) -> RecommendSuppliersWithEvidenceResult:
        scope = f"物品名称包含“{args.item_name}”的" if args.item_name else "全部"
        question = (
            f"统计{scope}供应商排名，返回 supplier_id、supplier_name、purchase_count、"
            "purchase_amount、average_delivery_days，按 purchase_count 降序，"
            f"最多 {args.top_k} 条。"
        )
        analysis = await self._analytics.execute(
            args=AnalyzeProcurementArgs(
                question=question, include_synthetic=args.include_synthetic
            ),
            context=context,
        )
        if analysis.status != "SUCCESS" or analysis.evidence is None:
            return RecommendSuppliersWithEvidenceResult(
                status=analysis.status, user_message=analysis.user_message
            )
        rows = analysis.evidence.result.rows[: args.top_k]
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )

        async def verify(row: dict[str, object]) -> SupplierEvidenceItem | None:
            raw_id = row.get("supplier_id")
            if not isinstance(raw_id, int):
                return None
            try:
                detail = await self._backend.get_supplier(identity=identity, supplier_id=raw_id)
            except BackendApplicationError:
                return SupplierEvidenceItem(
                    supplier_id=raw_id,
                    supplier_name=str(row.get("supplier_name") or raw_id),
                    purchase_count=_as_int(row.get("purchase_count")),
                    purchase_amount=row.get("purchase_amount"),
                    average_delivery_days=row.get("average_delivery_days"),
                    eligible=False,
                    verification_status="UNVERIFIED",
                )
            blacklisted = bool(detail.blacklist and detail.blacklist.active)
            return SupplierEvidenceItem(
                supplier_id=detail.supplier_id,
                supplier_name=detail.supplier_name,
                purchase_count=_as_int(row.get("purchase_count")),
                purchase_amount=row.get("purchase_amount"),
                average_delivery_days=row.get("average_delivery_days"),
                eligible=not blacklisted,
                verification_status="BLACKLISTED" if blacklisted else "VERIFIED",
            )

        verified = await asyncio.gather(*(verify(dict(row)) for row in rows))
        items = tuple(item for item in verified if item is not None and item.eligible)
        return RecommendSuppliersWithEvidenceResult(
            status="SUCCESS" if items else "NOT_FOUND",
            user_message=None if items else "没有通过资格核验的供应商",
            evidence=SupplierRecommendationEvidence(
                analytics=analysis.evidence,
                candidates=items,
                excluded_count=len(rows) - len(items),
            ),
        )


def _as_int(value: object) -> int:
    return int(value) if isinstance(value, (int, str)) else 0
