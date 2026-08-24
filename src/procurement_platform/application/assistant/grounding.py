from dataclasses import dataclass
from enum import StrEnum


class GroundingRequirement(StrEnum):
    NONE = "NONE"
    BACKEND_FACT = "BACKEND_FACT"
    SUPPLIER_RECOMMENDATION = "SUPPLIER_RECOMMENDATION"
    PRODUCT_RECOMMENDATION = "PRODUCT_RECOMMENDATION"
    SUPPLIER_COMPARISON = "SUPPLIER_COMPARISON"
    PRODUCT_COMPARISON = "PRODUCT_COMPARISON"
    PURCHASE_HISTORY = "PURCHASE_HISTORY"


@dataclass(frozen=True, slots=True)
class GroundingDecision:
    requirement: GroundingRequirement
    relevant_tool_names: frozenset[str] = frozenset()

    @property
    def required(self) -> bool:
        return self.requirement is not GroundingRequirement.NONE


_RELEVANT_TOOLS: dict[GroundingRequirement, frozenset[str]] = {
    GroundingRequirement.BACKEND_FACT: frozenset(
        {"search_purchase_requests", "get_purchase_request", "get_purchase_timeline"}
    ),
    GroundingRequirement.SUPPLIER_RECOMMENDATION: frozenset(
        {
            "recommend_suppliers",
            "recommend_suppliers_with_evidence",
            "get_supplier_profile",
            "find_similar_purchases",
        }
    ),
    GroundingRequirement.PRODUCT_RECOMMENDATION: frozenset(
        {
            "recommend_products",
            "recommend_products_by_name",
            "diagnose_procurement_need",
            "find_similar_purchases",
        }
    ),
    GroundingRequirement.SUPPLIER_COMPARISON: frozenset(
        {"compare_suppliers", "get_supplier_profile", "recommend_suppliers"}
    ),
    GroundingRequirement.PRODUCT_COMPARISON: frozenset(
        {"compare_products", "recommend_products", "find_similar_purchases"}
    ),
    GroundingRequirement.PURCHASE_HISTORY: frozenset(
        {
            "find_similar_purchases",
            "search_purchase_requests",
            "get_purchase_request",
            "get_purchase_timeline",
        }
    ),
}


class GroundingPolicy:
    """Deterministically identifies requests that require authoritative tool evidence."""

    def decide(self, user_text: str, *, available_tools: frozenset[str]) -> GroundingDecision:
        requirement = self._requirement_for(user_text.casefold().strip())
        if requirement is GroundingRequirement.NONE:
            return GroundingDecision(requirement=requirement)
        return GroundingDecision(
            requirement=requirement,
            relevant_tool_names=_RELEVANT_TOOLS[requirement].intersection(available_tools),
        )

    @staticmethod
    def _requirement_for(text: str) -> GroundingRequirement:
        supplier_terms = ("supplier", "vendor", "供应商", "厂商")
        product_terms = ("product", "model", "switch", "产品", "型号", "设备", "交换机")
        comparison_terms = ("compare", "comparison", "better", "对比", "比较", "哪个好")
        recommendation_terms = (
            "recommend",
            "suggest",
            "suitable",
            "should we consider",
            "推荐",
            "建议",
            "合适",
            "候选",
        )
        history_terms = (
            "last quarter",
            "last time",
            "previously",
            "purchased before",
            "purchase history",
            "上季度",
            "上次",
            "以前",
            "历史采购",
            "采购过",
        )
        fact_subject_terms = (
            "purchase request",
            "procurement request",
            "request pr-",
            "采购单",
            "采购申请",
            "单子",
        )
        fact_terms = (
            "status",
            "stage",
            "approved",
            "selected supplier",
            "what items",
            "how much",
            "query",
            "list",
            "show me",
            "current handler",
            "状态",
            "阶段",
            "谁审批",
            "谁批准",
            "选了哪",
            "采购了什么",
            "金额",
            "查询",
            "查看",
            "有哪些",
            "处理人",
        )

        has_supplier = _contains_any(text, supplier_terms)
        has_product = _contains_any(text, product_terms)
        if _contains_any(text, comparison_terms):
            if has_supplier:
                return GroundingRequirement.SUPPLIER_COMPARISON
            if has_product:
                return GroundingRequirement.PRODUCT_COMPARISON
        if _contains_any(text, recommendation_terms):
            if has_supplier:
                return GroundingRequirement.SUPPLIER_RECOMMENDATION
            if has_product:
                return GroundingRequirement.PRODUCT_RECOMMENDATION
        if _contains_any(text, history_terms):
            return GroundingRequirement.PURCHASE_HISTORY
        if _contains_any(text, fact_subject_terms) and _contains_any(text, fact_terms):
            return GroundingRequirement.BACKEND_FACT
        if _contains_any(
            text,
            (
                "selected supplier",
                "supplier was selected",
                "who approved",
                "how much was approved",
                "current procurement stage",
                "当前采购阶段",
                "批准金额",
            ),
        ):
            return GroundingRequirement.BACKEND_FACT
        return GroundingRequirement.NONE


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
