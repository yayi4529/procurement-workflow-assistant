from datetime import timedelta
from decimal import Decimal
from statistics import median

from app.services.recommendation.types import SupplierCandidate, SupplierFeatures, WarningCode


def _decimal_median(values: list[Decimal]) -> Decimal:
    return Decimal(median(values))


class FeatureAggregator:
    def supplier(self, candidate: SupplierCandidate) -> SupplierFeatures:
        evidence = candidate.evidence
        prices = [
            row.actual_unit_price
            for row in evidence
            if row.actual_unit_price is not None and row.actual_unit_price > 0
        ]
        priced_rows = sorted(
            (
                row
                for row in evidence
                if row.actual_unit_price is not None and row.actual_unit_price > 0
            ),
            key=lambda row: (row.purchased_at, row.execution_id),
        )
        delivery_days: list[Decimal] = []
        for row in evidence:
            if not row.requires_warehouse or row.final_received_at is None:
                continue
            elapsed: timedelta = row.final_received_at - row.purchased_at
            days = Decimal(str(elapsed.total_seconds())) / Decimal("86400")
            if days > 0:
                delivery_days.append(days)
        warnings = set(candidate.warnings)
        if not prices:
            warnings.add(WarningCode.NO_PRICE_DATA)
        if not delivery_days:
            warnings.add(WarningCode.NO_DELIVERY_DATA)
        return SupplierFeatures(
            supplier_id=candidate.supplier_id,
            history_purchase_count=candidate.historical_purchase_count,
            last_purchase_at=max(row.purchased_at for row in evidence),
            median_unit_price=_decimal_median(prices) if prices else None,
            min_unit_price=min(prices) if prices else None,
            max_unit_price=max(prices) if prices else None,
            latest_unit_price=priced_rows[-1].actual_unit_price if priced_rows else None,
            price_sample_count=len(prices),
            median_delivery_days=_decimal_median(delivery_days) if delivery_days else None,
            delivery_sample_count=len(delivery_days),
            evidence_count=len(evidence),
            warnings=frozenset(warnings),
        )
