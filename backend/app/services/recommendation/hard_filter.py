from app.services.recommendation.types import (
    ExcludedSupplierCandidate,
    ExclusionCode,
    SupplierCandidate,
    SupplierFilterResult,
)

_REASONS = {
    ExclusionCode.ACTIVE_BLACKLIST: "供应商当前处于有效黑名单",
    ExclusionCode.SUPPLIER_INACTIVE: "供应商当前不可采购",
    ExclusionCode.NO_EXECUTION_HISTORY: "供应商没有真实采购执行记录",
}


class HardFilter:
    def suppliers(self, candidates: list[SupplierCandidate]) -> SupplierFilterResult:
        eligible: list[SupplierCandidate] = []
        excluded: list[ExcludedSupplierCandidate] = []
        for candidate in candidates:
            code: ExclusionCode | None = None
            if candidate.active_blacklist:
                code = ExclusionCode.ACTIVE_BLACKLIST
            elif not candidate.supplier_active:
                code = ExclusionCode.SUPPLIER_INACTIVE
            elif not candidate.execution_ids:
                code = ExclusionCode.NO_EXECUTION_HISTORY
            if code is None:
                eligible.append(candidate)
            else:
                excluded.append(
                    ExcludedSupplierCandidate(
                        supplier_id=candidate.supplier_id,
                        supplier_name=candidate.supplier_name,
                        match_level=candidate.best_match_level,
                        exclusion_code=code,
                        exclusion_reason=_REASONS[code],
                    )
                )
        return SupplierFilterResult(eligible, excluded)
