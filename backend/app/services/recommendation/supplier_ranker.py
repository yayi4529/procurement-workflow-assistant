from decimal import Decimal

from app.services.recommendation.types import (
    MAX_SUPPLIER_RECOMMENDATIONS,
    RankedSupplier,
    SupplierCandidate,
    SupplierFeatures,
    SupplierScoreBreakdown,
)


def confidence_score(count: int) -> Decimal:
    if count >= 7:
        return Decimal("100")
    if count >= 4:
        return Decimal("80")
    if count >= 2:
        return Decimal("60")
    return Decimal("40")


def _ratio_score(minimum: Decimal, value: Decimal) -> Decimal:
    return min(Decimal("100"), max(Decimal("0"), Decimal("100") * minimum / value))


class SupplierRanker:
    def rank(
        self,
        candidates: list[SupplierCandidate],
        features: list[SupplierFeatures],
        *,
        limit: int = MAX_SUPPLIER_RECOMMENDATIONS,
    ) -> list[RankedSupplier]:
        by_id = {item.supplier_id: item for item in features}
        valid_prices = [
            item.median_unit_price
            for item in features
            if item.median_unit_price is not None and item.median_unit_price > 0
        ]
        valid_delivery = [
            item.median_delivery_days
            for item in features
            if item.median_delivery_days is not None and item.median_delivery_days > 0
        ]
        min_price = min(valid_prices) if valid_prices else None
        min_delivery = min(valid_delivery) if valid_delivery else None
        scored: list[
            tuple[SupplierCandidate, SupplierFeatures, Decimal, SupplierScoreBreakdown]
        ] = []
        for candidate in candidates:
            feature = by_id[candidate.supplier_id]
            price = (
                _ratio_score(min_price, feature.median_unit_price)
                if min_price is not None and feature.median_unit_price is not None
                else None
            )
            delivery = (
                _ratio_score(min_delivery, feature.median_delivery_days)
                if min_delivery is not None and feature.median_delivery_days is not None
                else None
            )
            confidence = confidence_score(feature.evidence_count)
            weights = {
                "relevance": Decimal("0.40"),
                "price": Decimal("0.30") if price is not None else Decimal("0"),
                "delivery": Decimal("0.20") if delivery is not None else Decimal("0"),
                "confidence": Decimal("0.10"),
            }
            total_weight = sum(weights.values(), start=Decimal("0"))
            score = (
                weights["relevance"] * candidate.relevance_score
                + weights["price"] * (price or Decimal("0"))
                + weights["delivery"] * (delivery or Decimal("0"))
                + weights["confidence"] * confidence
            ) / total_weight
            breakdown = SupplierScoreBreakdown(
                relevance_score=candidate.relevance_score,
                price_score=price,
                delivery_score=delivery,
                confidence_score=confidence,
                relevance_weight=weights["relevance"] / total_weight,
                price_weight=weights["price"] / total_weight,
                delivery_weight=weights["delivery"] / total_weight,
                confidence_weight=weights["confidence"] / total_weight,
            )
            scored.append((candidate, feature, score, breakdown))
        scored.sort(
            key=lambda row: (
                -row[2],
                -row[3].relevance_score,
                -row[3].confidence_score,
                row[1].median_unit_price is None,
                row[1].median_unit_price or Decimal("Infinity"),
                row[1].median_delivery_days is None,
                row[1].median_delivery_days or Decimal("Infinity"),
                row[0].supplier_id,
            )
        )
        return [
            RankedSupplier(index, candidate, feature, score, breakdown)
            for index, (candidate, feature, score, breakdown) in enumerate(
                scored[: min(limit, MAX_SUPPLIER_RECOMMENDATIONS)], start=1
            )
        ]
