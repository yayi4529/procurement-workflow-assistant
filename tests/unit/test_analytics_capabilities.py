from datetime import UTC, datetime

import pytest

from procurement_platform.adapters.backend.fake_client import FakeBackendClient
from procurement_platform.application.assistant.capabilities.analytics import (
    DescribeAnalyticsSchemaArgs,
    DescribeAnalyticsSchemaCapability,
    RunReadonlyAnalyticsSqlArgs,
    RunReadonlyAnalyticsSqlCapability,
)
from procurement_platform.domain.analytics import AnalyticsQueryResult
from procurement_platform.domain.assistant import AssistantToolContext
from procurement_platform.domain.enums import RoleCode
from procurement_platform.domain.user import CurrentUser, UserRole

QUERY_SQL = (
    "SELECT item_name, COUNT(*) purchase_count FROM analytics_purchase_item_fact GROUP BY item_name"
)


def purchaser() -> CurrentUser:
    return CurrentUser(
        employee_id=9,
        name="采购员",
        mobile=None,
        status="ACTIVE",
        roles=(UserRole(role_code=RoleCode.PURCHASER),),
        buildings=(),
    )


def context(user: CurrentUser) -> AssistantToolContext:
    return AssistantToolContext(
        platform_type="FEISHU",
        platform_user_id="ou_analytics",
        conversation_id=1,
        external_conversation_id="oc_analytics",
        external_message_id="om_analytics",
        current_time=datetime(2026, 8, 23, tzinfo=UTC),
        timezone_name="Asia/Shanghai",
        current_user=user,
    )


@pytest.mark.asyncio
async def test_analytics_capabilities_return_backend_evidence() -> None:
    user = purchaser()
    backend = FakeBackendClient(user)
    backend.analytics_query_result = AnalyticsQueryResult(
        query_id="q-1",
        columns=("item_name", "purchase_count"),
        rows=({"item_name": "控制电源", "purchase_count": 8},),
        row_count=1,
        truncated=False,
        duration_ms=3,
        normalized_sql=QUERY_SQL,
        synthetic_included=True,
    )

    catalog = await DescribeAnalyticsSchemaCapability(backend).execute(
        args=DescribeAnalyticsSchemaArgs(), context=context(user)
    )
    query = await RunReadonlyAnalyticsSqlCapability(backend).execute(
        args=RunReadonlyAnalyticsSqlArgs(
            question="各物品采购次数",
            sql=QUERY_SQL,
        ),
        context=context(user),
    )

    assert catalog.status == "SUCCESS"
    assert query.result is not None
    assert query.result.rows[0]["purchase_count"] == 8
    assert backend.call_counts["get_analytics_catalog"] == 1
    assert backend.call_counts["run_analytics_query"] == 1
