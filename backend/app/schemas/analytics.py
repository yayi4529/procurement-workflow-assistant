from pydantic import BaseModel, Field

type AnalyticsScalar = str | int | float | bool | None


class AnalyticsField(BaseModel):
    name: str
    description: str
    data_type: str


class AnalyticsView(BaseModel):
    name: str
    description: str
    grain: str
    fields: list[AnalyticsField]


class AnalyticsMetric(BaseModel):
    name: str
    description: str
    expression: str


class AnalyticsCatalogData(BaseModel):
    version: str
    dialect: str
    synthetic_default_included: bool
    views: list[AnalyticsView]
    metrics: list[AnalyticsMetric]


class AnalyticsQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    sql: str = Field(min_length=1, max_length=20_000)
    include_synthetic: bool | None = None


class AnalyticsQueryData(BaseModel):
    query_id: str
    columns: list[str]
    rows: list[dict[str, AnalyticsScalar]]
    row_count: int
    truncated: bool
    duration_ms: int
    normalized_sql: str
    synthetic_included: bool
