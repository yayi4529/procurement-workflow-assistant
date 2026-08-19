from pathlib import Path

import pytest

from procurement_platform.adapters.knowledge import MarkdownKnowledgeLoader
from procurement_platform.application.fault_guidance import MarkdownKnowledgeSearch


def _write_knowledge(
    root: Path,
    *,
    filename: str = "knowledge.md",
    knowledge_id: str | None = "UPS-BATTERY-001",
    category: str = "UPS",
    status: str = "ACTIVE",
    risk_level: str = "MEDIUM",
    schema_version: int = 1,
) -> None:
    id_line = f"knowledge_id: {knowledge_id}\n" if knowledge_id is not None else ""
    (root / filename).write_text(
        "---\n"
        f"schema_version: {schema_version}\n"
        f"{id_line}"
        "title: UPS蓄电池异常与BATTERY FAULT\n"
        f"equipment_category: {category}\n"
        "knowledge_type: FAULT_GUIDE\n"
        "aliases:\n"
        "  - BATTERY FAULT\n"
        "  - 电池报警\n"
        f"risk_level: {risk_level}\n"
        f"status: {status}\n"
        "version: 1\n"
        "---\n"
        "# UPS蓄电池异常与BATTERY FAULT\n\n"
        "UPS 后备时间明显下降。\n",
        encoding="utf-8",
    )


def test_loader_reads_active_front_matter_and_content(tmp_path: Path) -> None:
    _write_knowledge(tmp_path)
    knowledge = MarkdownKnowledgeLoader(tmp_path).load().get("UPS-BATTERY-001")
    assert knowledge is not None
    assert knowledge.title == "UPS蓄电池异常与BATTERY FAULT"
    assert knowledge.aliases == ["BATTERY FAULT", "电池报警"]
    assert knowledge.content.startswith("# UPS蓄电池异常")


def test_repository_knowledge_file_is_loadable() -> None:
    root = Path(__file__).resolve().parents[2] / "knowledge" / "fault-guidance"
    knowledge = MarkdownKnowledgeLoader(root).load().get("UPS-BATTERY-001")
    assert knowledge is not None
    assert knowledge.equipment_category == "UPS"


def test_loader_excludes_inactive_knowledge(tmp_path: Path) -> None:
    _write_knowledge(tmp_path, status="INACTIVE")
    assert MarkdownKnowledgeLoader(tmp_path).load().list_all() == []


def test_loader_skips_invalid_documents_without_losing_valid_one(tmp_path: Path) -> None:
    _write_knowledge(tmp_path, filename="valid.md")
    _write_knowledge(tmp_path, filename="missing-id.md", knowledge_id=None)
    _write_knowledge(tmp_path, filename="bad-risk.md", risk_level="CRITICAL")
    _write_knowledge(tmp_path, filename="bad-schema.md", schema_version=2)
    repository = MarkdownKnowledgeLoader(tmp_path).load()
    assert [item.knowledge_id for item in repository.list_all()] == ["UPS-BATTERY-001"]


def test_loader_reports_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError, match="fault knowledge directory"):
        MarkdownKnowledgeLoader(missing).load()


def test_search_alias_category_global_and_unrelated_cases(tmp_path: Path) -> None:
    _write_knowledge(tmp_path)
    search = MarkdownKnowledgeSearch(MarkdownKnowledgeLoader(tmp_path).load())
    exact = search.search(query="BATTERY FAULT", equipment_category="UPS")
    assert [item.knowledge_id for item in exact] == ["UPS-BATTERY-001"]
    assert exact[0].matched_aliases == ["BATTERY FAULT"]
    assert (
        search.search(query="2号UPS最近报BATTERY FAULT", equipment_category="UPS")[0].knowledge_id
        == "UPS-BATTERY-001"
    )
    assert search.search(query="电池报警", equipment_category="UPS")[0].knowledge_id == (
        "UPS-BATTERY-001"
    )
    assert search.search(query="BATTERY FAULT", equipment_category="SERVER") == []
    assert search.search(query="BATTERY FAULT", equipment_category=None)[0].knowledge_id == (
        "UPS-BATTERY-001"
    )
    assert search.search(query="柴油发电机燃油泄漏", equipment_category=None) == []


def test_search_normalizes_case_whitespace_and_punctuation(tmp_path: Path) -> None:
    _write_knowledge(tmp_path)
    search = MarkdownKnowledgeSearch(MarkdownKnowledgeLoader(tmp_path).load())
    result = search.search(query=" Battery,   Fault! ", equipment_category="ups")
    assert result[0].matched_aliases == ["BATTERY FAULT"]
