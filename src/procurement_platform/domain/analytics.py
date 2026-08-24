from typing import TypeAlias

from pydantic import BaseModel, ConfigDict

AnalyticsScalar: TypeAlias = str | int | float | bool | None


class AnalyticsField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    description: str
    data_type: str


class AnalyticsView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    description: str
    grain: str
    fields: tuple[AnalyticsField, ...]


class AnalyticsMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    description: str
    expression: str


class AnalyticsCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: str
    dialect: str
    synthetic_default_included: bool
    views: tuple[AnalyticsView, ...]
    metrics: tuple[AnalyticsMetric, ...]


class AnalyticsQueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    query_id: str
    columns: tuple[str, ...]
    rows: tuple[dict[str, AnalyticsScalar], ...]
    row_count: int
    truncated: bool
    duration_ms: int
    normalized_sql: str
    synthetic_included: bool
