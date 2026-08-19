from calendar import monthrange
from datetime import datetime
from decimal import Decimal

from app.services.recommendation.types import (
    MAX_PRODUCT_RECOMMENDATIONS,
    ProductCandidate,
    ProductScoreBreakdown,
    RankedProduct,
)


def months_before(value: datetime, months: int) -> datetime:
    total = value.year * 12 + value.month - 1 - months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def frequency_score(count: int) -> Decimal:
    if count >= 7:
        return Decimal("100")
    if count >= 4:
        return Decimal("80")
    if count >= 2:
        return Decimal("60")
    return Decimal("40")


def recency_score(last_purchased_at: datetime, now: datetime) -> Decimal:
    if last_purchased_at >= months_before(now, 6):
        return Decimal("100")
    if last_purchased_at >= months_before(now, 12):
        return Decimal("80")
    if last_purchased_at >= months_before(now, 24):
        return Decimal("60")
    return Decimal("40")


def coverage_score(count: int) -> Decimal:
    if count >= 3:
        return Decimal("100")
    if count == 2:
        return Decimal("70")
    if count == 1:
        return Decimal("40")
    return Decimal("0")


class ProductRanker:
    def rank(
        self,
        candidates: list[ProductCandidate],
        *,
        now: datetime,
        limit: int = MAX_PRODUCT_RECOMMENDATIONS,
    ) -> list[RankedProduct]:
        scored: list[tuple[ProductCandidate, Decimal, ProductScoreBreakdown]] = []
        for candidate in candidates:
            frequency = frequency_score(candidate.historical_purchase_count)
            recency = recency_score(candidate.last_purchased_at, now)
            coverage = coverage_score(len(candidate.active_supplier_ids))
            score = (
                Decimal("0.50") * candidate.relevance_score
                + Decimal("0.20") * frequency
                + Decimal("0.15") * recency
                + Decimal("0.15") * coverage
            )
            scored.append(
                (
                    candidate,
                    score,
                    ProductScoreBreakdown(candidate.relevance_score, frequency, recency, coverage),
                )
            )
        scored.sort(
            key=lambda row: (
                -row[1],
                -row[2].relevance_score,
                -row[2].frequency_score,
                -row[2].recency_score,
                -row[2].supplier_coverage_score,
                row[0].product_key,
            )
        )
        return [
            RankedProduct(index, candidate, score, breakdown)
            for index, (candidate, score, breakdown) in enumerate(
                scored[: min(limit, MAX_PRODUCT_RECOMMENDATIONS)], start=1
            )
        ]
