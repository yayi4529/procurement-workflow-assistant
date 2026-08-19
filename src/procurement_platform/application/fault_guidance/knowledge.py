import logging
import re
from collections.abc import Iterable

from procurement_platform.domain.fault_guidance import (
    FaultKnowledge,
    KnowledgeSearchResult,
)

logger = logging.getLogger(__name__)

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")
_MIN_PARTIAL_QUERY_LENGTH = 3


def _normalize(value: str) -> str:
    without_punctuation = _PUNCTUATION.sub(" ", value.casefold())
    return _WHITESPACE.sub(" ", without_punctuation).strip()


class FaultKnowledgeRepository:
    def __init__(self, knowledge: Iterable[FaultKnowledge] = ()) -> None:
        self._knowledge = {item.knowledge_id: item for item in knowledge}

    def get(self, knowledge_id: str) -> FaultKnowledge | None:
        return self._knowledge.get(knowledge_id)

    def list_all(self) -> list[FaultKnowledge]:
        return list(self._knowledge.values())


class MarkdownKnowledgeSearch:
    def __init__(self, repository: FaultKnowledgeRepository) -> None:
        self._repository = repository

    def search(
        self,
        *,
        query: str,
        equipment_category: str | None = None,
        top_k: int = 3,
    ) -> list[KnowledgeSearchResult]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        normalized_query = _normalize(query)
        if not normalized_query:
            return []
        normalized_category = equipment_category.strip().upper() if equipment_category else None
        candidates = [
            item
            for item in self._repository.list_all()
            if normalized_category is None or item.equipment_category.upper() == normalized_category
        ]

        alias_matches: list[tuple[FaultKnowledge, list[str]]] = []
        for item in candidates:
            matched = [
                alias
                for alias in item.aliases
                if self._matches_alias(normalized_query, _normalize(alias))
            ]
            if matched:
                alias_matches.append((item, matched))
        if alias_matches:
            results = [self._result(item, aliases) for item, aliases in alias_matches[:top_k]]
            logger.info("fault knowledge search matched %d document(s)", len(results))
            return results

        fallback = [
            item
            for item in candidates
            if normalized_query in _normalize(item.title)
            or normalized_query in _normalize(item.content)
        ]
        results = [self._result(item, []) for item in fallback[:top_k]]
        if results:
            logger.info("fault knowledge fallback matched %d document(s)", len(results))
        else:
            logger.info("fault knowledge search returned no matches")
        return results

    @staticmethod
    def _matches_alias(query: str, alias: str) -> bool:
        if not alias:
            return False
        if alias in query:
            return True
        return len(query) >= _MIN_PARTIAL_QUERY_LENGTH and query in alias

    @staticmethod
    def _result(item: FaultKnowledge, aliases: list[str]) -> KnowledgeSearchResult:
        return KnowledgeSearchResult(
            knowledge_id=item.knowledge_id,
            title=item.title,
            equipment_category=item.equipment_category,
            risk_level=item.risk_level,
            matched_aliases=aliases,
            content=item.content,
        )
