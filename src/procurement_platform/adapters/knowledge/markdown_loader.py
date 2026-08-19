import logging
from pathlib import Path
from typing import Any

import yaml

from procurement_platform.application.fault_guidance.knowledge import (
    FaultKnowledgeRepository,
)
from procurement_platform.domain.fault_guidance import FaultKnowledge

logger = logging.getLogger(__name__)

_SUPPORTED_SCHEMA_VERSION = 1
_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}
_STATUSES = {"ACTIVE", "INACTIVE"}


class MarkdownKnowledgeLoader:
    def __init__(self, root_path: str | Path) -> None:
        self._root_path = Path(root_path)

    def load(self) -> FaultKnowledgeRepository:
        if not self._root_path.is_dir():
            raise FileNotFoundError(f"fault knowledge directory does not exist: {self._root_path}")
        loaded: list[FaultKnowledge] = []
        for path in sorted(self._root_path.rglob("*.md")):
            knowledge_id: str | None = None
            try:
                metadata, content = self._parse(path)
                raw_id = metadata.get("knowledge_id")
                knowledge_id = raw_id if isinstance(raw_id, str) else None
                knowledge, active = self._validate(metadata, content)
                if active:
                    loaded.append(knowledge)
            except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
                logger.warning(
                    "skipping invalid fault knowledge path=%s knowledge_id=%s reason=%s",
                    path,
                    knowledge_id,
                    exc,
                )
        logger.info("fault knowledge loading completed loaded_count=%d", len(loaded))
        return FaultKnowledgeRepository(loaded)

    @staticmethod
    def _parse(path: Path) -> tuple[dict[str, Any], str]:
        raw = path.read_text(encoding="utf-8")
        lines = raw.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError("YAML front matter opening delimiter is missing")
        try:
            closing_index = next(
                index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
            )
        except StopIteration as exc:
            raise ValueError("YAML front matter closing delimiter is missing") from exc
        parsed = yaml.safe_load("\n".join(lines[1:closing_index]))
        if not isinstance(parsed, dict):
            raise ValueError("YAML front matter must be a mapping")
        return parsed, "\n".join(lines[closing_index + 1 :]).strip()

    @staticmethod
    def _validate(metadata: dict[str, Any], content: str) -> tuple[FaultKnowledge, bool]:
        if metadata.get("schema_version") != _SUPPORTED_SCHEMA_VERSION:
            raise ValueError("unsupported schema_version")
        knowledge_id = _required_text(metadata, "knowledge_id")
        title = _required_text(metadata, "title")
        equipment_category = _required_text(metadata, "equipment_category")
        knowledge_type = _required_text(metadata, "knowledge_type")
        if knowledge_type != "FAULT_GUIDE":
            raise ValueError("knowledge_type must be FAULT_GUIDE")
        aliases_value = metadata.get("aliases")
        if not isinstance(aliases_value, list):
            raise ValueError("aliases must be a list")
        aliases = [item.strip() for item in aliases_value if isinstance(item, str) and item.strip()]
        if not aliases or len(aliases) != len(aliases_value):
            raise ValueError("aliases must contain valid non-empty strings")
        risk_level = _required_text(metadata, "risk_level")
        if risk_level not in _RISK_LEVELS:
            raise ValueError("invalid risk_level")
        status = _required_text(metadata, "status")
        if status not in _STATUSES:
            raise ValueError("invalid status")
        version = metadata.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("version must be a positive integer")
        if not content:
            raise ValueError("Markdown content must not be empty")
        return (
            FaultKnowledge(
                knowledge_id=knowledge_id,
                title=title,
                equipment_category=equipment_category,
                knowledge_type=knowledge_type,
                aliases=aliases,
                risk_level=risk_level,
                version=version,
                content=content,
            ),
            status == "ACTIVE",
        )


def _required_text(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()
