from pydantic import Field

from procurement_platform.application.assistant.tooling.common import StrictArgs
from procurement_platform.domain.analytics import AnalyticsCatalog, AnalyticsQueryResult
from procurement_platform.domain.assistant import AssistantToolContext, AssistantToolResult
from procurement_platform.domain.enums import PlatformType
from procurement_platform.domain.errors import BackendApplicationError
from procurement_platform.domain.identity import PlatformIdentity
from procurement_platform.ports.backend_client import BackendClient


class DescribeAnalyticsSchemaArgs(StrictArgs):
    pass


class DescribeAnalyticsSchemaResult(AssistantToolResult):
    catalog: AnalyticsCatalog | None = None


class DescribeAnalyticsSchemaCapability:
    name = "describe_analytics_schema"
    side_effect = "READ"
    description = (
        "Read the governed procurement analytics schema, field meanings and metric definitions. "
        "Call this before writing analytics SQL. Available only to purchasers and administrators."
    )
    args_model = DescribeAnalyticsSchemaArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def execute(
        self, *, args: DescribeAnalyticsSchemaArgs, context: AssistantToolContext
    ) -> DescribeAnalyticsSchemaResult:
        del args
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        try:
            return DescribeAnalyticsSchemaResult(
                status="SUCCESS",
                catalog=await self._backend.get_analytics_catalog(identity=identity),
            )
        except BackendApplicationError as exc:
            status = (
                "PERMISSION_DENIED"
                if exc.error_code == "PERMISSION_DENIED"
                else "BACKEND_UNAVAILABLE"
            )
            return DescribeAnalyticsSchemaResult(status=status, user_message=exc.user_message)


class RunReadonlyAnalyticsSqlArgs(StrictArgs):
    question: str = Field(min_length=1, max_length=1000)
    sql: str = Field(min_length=1, max_length=20_000)
    include_synthetic: bool | None = None


class RunReadonlyAnalyticsSqlResult(AssistantToolResult):
    result: AnalyticsQueryResult | None = None


class RunReadonlyAnalyticsSqlCapability:
    name = "run_readonly_analytics_sql"
    side_effect = "READ"
    description = (
        "Execute one governed read-only MySQL analytics query after describe_analytics_schema. "
        "Use SQL aggregation for counts, rankings, trends, prices, product and supplier "
        "recommendations. "
        "Never query raw tables. Results are evidence; do not invent missing values."
    )
    args_model = RunReadonlyAnalyticsSqlArgs

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def execute(
        self, *, args: RunReadonlyAnalyticsSqlArgs, context: AssistantToolContext
    ) -> RunReadonlyAnalyticsSqlResult:
        identity = PlatformIdentity.create(
            PlatformType(context.platform_type), context.platform_user_id
        )
        try:
            result = await self._backend.run_analytics_query(
                identity=identity,
                question=args.question,
                sql=args.sql,
                include_synthetic=args.include_synthetic,
            )
            return RunReadonlyAnalyticsSqlResult(status="SUCCESS", result=result)
        except BackendApplicationError as exc:
            if exc.error_code == "PERMISSION_DENIED":
                return RunReadonlyAnalyticsSqlResult(
                    status="PERMISSION_DENIED", user_message=exc.user_message
                )
            return RunReadonlyAnalyticsSqlResult(
                status="INVALID_ARGUMENTS", user_message=exc.user_message
            )
