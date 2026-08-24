import pytest

from app.core.exceptions import AppError
from app.services.analytics import AnalyticsSqlValidator


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE analytics_purchase_item_fact SET item_name='x'",
        "SELECT * FROM purchase_request",
        "SELECT * FROM information_schema.tables",
        "SELECT SLEEP(1) FROM analytics_purchase_item_fact",
        "SELECT * FROM analytics_purchase_item_fact FOR UPDATE",
        "SELECT * FROM analytics_purchase_item_fact INTO OUTFILE '/tmp/analytics.csv'",
        "SELECT * FROM analytics_purchase_item_fact; SELECT 1",
    ],
)
def test_validator_rejects_non_governed_sql(sql: str) -> None:
    with pytest.raises(AppError):
        AnalyticsSqlValidator().validate(sql, include_synthetic=True)


def test_validator_accepts_aggregate_and_normalizes_mysql() -> None:
    sql = AnalyticsSqlValidator().validate(
        "SELECT item_name, COUNT(*) AS purchase_count, SUM(requested_quantity) AS total_quantity "
        "FROM analytics_purchase_item_fact GROUP BY item_name ORDER BY purchase_count DESC",
        include_synthetic=True,
    )
    assert "analytics_purchase_item_fact" in sql
    assert "GROUP BY item_name" in sql


def test_validator_switches_to_real_only_view() -> None:
    sql = AnalyticsSqlValidator().validate(
        "SELECT COUNT(*) AS count FROM analytics_purchase_request_fact",
        include_synthetic=False,
    )
    assert "analytics_purchase_request_fact_real" in sql


def test_validator_allows_cte_over_governed_view() -> None:
    sql = AnalyticsSqlValidator().validate(
        "WITH totals AS (SELECT supplier_name, SUM(actual_total_price) amount "
        "FROM analytics_purchase_item_fact GROUP BY supplier_name) "
        "SELECT * FROM totals ORDER BY amount DESC",
        include_synthetic=True,
    )
    assert sql.startswith("WITH totals AS")
