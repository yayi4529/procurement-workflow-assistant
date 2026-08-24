from typing import Protocol

from procurement_platform.domain.assistant import AssistantToolResult


class EvidenceReferenceExtractor(Protocol):
    def extract(self, *, capability_name: str, result: AssistantToolResult) -> tuple[str, ...]: ...


class EvidenceReferenceExtractorRegistry:
    """Extract only explicitly supported, non-sensitive backend identifiers."""

    def extract(self, *, capability_name: str, result: AssistantToolResult) -> tuple[str, ...]:
        refs: list[str] = []
        if capability_name == "analyze_procurement":
            evidence = getattr(result, "evidence", None)
            query = getattr(evidence, "result", None)
            query_id = getattr(query, "query_id", None)
            if isinstance(query_id, str):
                refs.append(f"analytics-query:{query_id}")
        elif capability_name == "recommend_suppliers_with_evidence":
            evidence = getattr(result, "evidence", None)
            analytics = getattr(evidence, "analytics", None)
            query = getattr(analytics, "result", None)
            query_id = getattr(query, "query_id", None)
            if isinstance(query_id, str):
                refs.append(f"analytics-query:{query_id}")
            for candidate in getattr(evidence, "candidates", ()):
                supplier_id = getattr(candidate, "supplier_id", None)
                if isinstance(supplier_id, int):
                    refs.append(f"supplier:{supplier_id}")
        elif capability_name in {
            "search_assets",
            "resolve_asset",
            "get_asset",
            "get_asset_components",
            "get_asset_relations",
        }:
            asset_facts = []
            asset = getattr(result, "asset", None)
            if asset is not None:
                asset_facts.append(asset)
            asset_facts.extend(getattr(result, "items", ()))
            asset_facts.extend(getattr(result, "candidates", ()))
            asset_ref = getattr(result, "asset_ref", None)
            if isinstance(asset_ref, str):
                refs.extend(self._stable_ref(asset_ref, "asset"))
            for fact in asset_facts:
                refs.extend(self._stable_ref(getattr(fact, "asset_ref", None), "asset"))
                refs.extend(self._stable_ref(getattr(fact, "model_ref", None), "model"))
        elif capability_name == "find_similar_purchases":
            for candidate in getattr(result, "candidates", ()):
                requirement_no = getattr(candidate, "requirement_no", None)
                if isinstance(requirement_no, str):
                    refs.append(f"history:{requirement_no}")
        elif capability_name in {"query_purchase_requests", "get_purchase_request"}:
            for record in getattr(result, "records", ()):
                requirement_id = getattr(record, "requirement_id", None)
                if isinstance(requirement_id, int):
                    refs.append(f"purchase-request:{requirement_id}")
        else:
            response = getattr(result, "response", None)
            for item in getattr(response, "items", ()) or getattr(response, "recommendations", ()):
                reference_id = getattr(item, "reference_id", None) or getattr(
                    item, "candidate_ref", None
                )
                model_id = getattr(item, "equipment_model_id", None)
                if isinstance(reference_id, str):
                    refs.append(f"recommendation:{reference_id}")
                if isinstance(model_id, int):
                    refs.append(f"catalog-model:{model_id}")
        return tuple(dict.fromkeys(refs))

    @staticmethod
    def _stable_ref(value: object, expected_prefix: str) -> tuple[str, ...]:
        if not isinstance(value, str):
            return ()
        prefix, separator, raw_id = value.partition(":")
        if separator != ":" or prefix != expected_prefix or not raw_id.isdecimal():
            return ()
        numeric_id = int(raw_id)
        if numeric_id <= 0:
            return ()
        output_prefix = "catalog-model" if expected_prefix == "model" else "asset"
        return (f"{output_prefix}:{numeric_id}",)
