import asyncio
import logging
import time
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlglot import exp, parse
from sqlglot.errors import ParseError

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.domain.identity import CurrentUser
from app.schemas.analytics import AnalyticsQueryData, AnalyticsQueryRequest, AnalyticsScalar
from app.services.analytics_catalog import analytics_catalog

logger = logging.getLogger(__name__)
ALLOWED_VIEWS = frozenset({"analytics_purchase_request_fact", "analytics_purchase_item_fact"})
DENIED_FUNCTIONS = frozenset({"sleep", "benchmark", "get_lock", "release_lock", "load_file"})


class AnalyticsSqlValidator:
    def validate(self, sql: str, *, include_synthetic: bool) -> str:
        try:
            statements = parse(sql, read="mysql")
        except ParseError as exc:
            raise AppError("ANALYTICS_SQL_INVALID", "分析 SQL 无法解析", 422) from exc
        if len(statements) != 1 or not isinstance(statements[0], exp.Query):
            raise AppError("ANALYTICS_SQL_NOT_READ_ONLY", "仅允许单条只读查询", 422)
        statement = statements[0]
        if statement.find(exp.Lock) is not None:
            raise AppError("ANALYTICS_SQL_NOT_READ_ONLY", "分析查询不能申请数据库锁", 422)
        tables = tuple(statement.find_all(exp.Table))
        cte_aliases = frozenset(cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE))
        source_tables = tuple(table for table in tables if table.name.lower() not in cte_aliases)
        if not source_tables or any(
            table.name.lower() not in ALLOWED_VIEWS or bool(table.db) for table in source_tables
        ):
            raise AppError("ANALYTICS_VIEW_NOT_ALLOWED", "查询只能使用授权分析视图", 422)
        for function in statement.find_all(exp.Func):
            function_name = (
                function.name if isinstance(function, exp.Anonymous) else function.sql_name()
            )
            if function_name.lower() in DENIED_FUNCTIONS:
                raise AppError("ANALYTICS_FUNCTION_NOT_ALLOWED", "查询包含禁止函数", 422)
        if not include_synthetic:
            for table in source_tables:
                table.set("this", exp.to_identifier(f"{table.name}_real"))
        return statement.sql(dialect="mysql", pretty=False)


class AnalyticsQueryService:
    def __init__(
        self, analytics_engine: AsyncEngine | None, settings: Settings | None = None
    ) -> None:
        self._engine = analytics_engine
        self._settings = settings or get_settings()
        self._validator = AnalyticsSqlValidator()

    def catalog(self, current_user: CurrentUser):
        self._authorize(current_user)
        self._ensure_enabled()
        return analytics_catalog(
            synthetic_default_included=(
                self._settings.app_env.lower() != "production"
                and self._settings.analytics_include_synthetic_default
            )
        )

    async def query(
        self,
        audit_session: AsyncSession,
        current_user: CurrentUser,
        payload: AnalyticsQueryRequest,
    ) -> AnalyticsQueryData:
        self._authorize(current_user)
        engine = self._ensure_enabled()
        include_synthetic = self._settings.app_env.lower() != "production" and (
            payload.include_synthetic
            if payload.include_synthetic is not None
            else self._settings.analytics_include_synthetic_default
        )
        normalized = self._validator.validate(payload.sql, include_synthetic=include_synthetic)
        query_id = str(uuid4())
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._settings.analytics_query_timeout_seconds):
                # MySQL requires underlying-table privileges to EXPLAIN a view. Use the
                # backend-owned transaction for the plan only; result rows are still read
                # exclusively through the restricted analytics connection.
                explain = await audit_session.execute(text(f"EXPLAIN {normalized}"))
                estimated = sum(int(row._mapping.get("rows") or 0) for row in explain)
                if estimated > self._settings.analytics_max_explain_rows:
                    raise AppError(
                        "ANALYTICS_QUERY_TOO_EXPENSIVE",
                        "分析查询预计扫描数据过多",
                        422,
                    )
                async with engine.connect() as connection:
                    result = await connection.execute(text(normalized))
                    raw_rows = result.mappings().fetchmany(self._settings.analytics_max_rows + 1)
        except TimeoutError as exc:
            self._log(
                current_user, query_id, payload.question, normalized, "TIMEOUT", started, 0, False
            )
            raise AppError("ANALYTICS_QUERY_TIMEOUT", "分析查询超时", 504) from exc
        except AppError:
            self._log(
                current_user, query_id, payload.question, normalized, "REJECTED", started, 0, False
            )
            raise
        except Exception as exc:
            self._log(
                current_user, query_id, payload.question, normalized, "FAILED", started, 0, False
            )
            raise AppError("ANALYTICS_QUERY_FAILED", "分析查询执行失败", 422) from exc
        truncated = len(raw_rows) > self._settings.analytics_max_rows
        selected_rows = raw_rows[: self._settings.analytics_max_rows]
        rows = [{key: self._scalar(value) for key, value in row.items()} for row in selected_rows]
        duration_ms = int((time.perf_counter() - started) * 1000)
        self._log(
            current_user,
            query_id,
            payload.question,
            normalized,
            "SUCCEEDED",
            started,
            len(rows),
            truncated,
        )
        return AnalyticsQueryData(
            query_id=query_id,
            columns=list(result.keys()),
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            duration_ms=duration_ms,
            normalized_sql=normalized,
            synthetic_included=include_synthetic,
        )

    def _authorize(self, current_user: CurrentUser) -> None:
        if not current_user.has_any_role("PURCHASER", "ADMIN"):
            raise AppError("PERMISSION_DENIED", "当前角色不能使用智能问数", 403)

    def _ensure_enabled(self) -> AsyncEngine:
        if not self._settings.analytics_enabled or self._engine is None:
            raise AppError("ANALYTICS_DISABLED", "智能问数尚未启用", 503)
        return self._engine

    @staticmethod
    def _scalar(value: object) -> AnalyticsScalar:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _log(
        user: CurrentUser,
        query_id: str,
        question: str,
        sql: str,
        status: str,
        started: float,
        row_count: int,
        truncated: bool,
    ) -> None:
        logger.info(
            "analytics_query",
            extra={
                "query_id": query_id,
                "employee_id": user.employee_id,
                "question": question,
                "normalized_sql": sql,
                "status": status,
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "row_count": row_count,
                "truncated": truncated,
            },
        )
