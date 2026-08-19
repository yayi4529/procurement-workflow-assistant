from __future__ import annotations

from pathlib import Path

from procurement_platform.adapters.knowledge import MarkdownKnowledgeLoader
from procurement_platform.application.fault_guidance import MarkdownKnowledgeSearch
from scripts.validate_fault_knowledge import (
    KnowledgeDocument,
    _validate_document,
    load_backend_categories,
    load_vocabulary,
    validate_repository,
)

ROOT = Path(__file__).resolve().parents[2]


def _catalogs() -> tuple[set[str], dict[str, dict[str, str]]]:
    categories = load_backend_categories(ROOT / "backend/scripts/seed_demo_data.py")
    vocabulary, issues = load_vocabulary(ROOT / "knowledge/catalog/procurement-vocabulary-v1.yaml")
    assert issues == []
    return categories, vocabulary


def _valid_ups_fan_document() -> KnowledgeDocument:
    sections = "\n\n".join(
        f"## {title}\n\n有效内容。"
        for title in (
            "场景说明",
            "典型现象",
            "需要关注的信息",
            "判断采购需求前建议确认的信息",
            "采购相关知识",
            "数量规则",
            "不应直接推断的内容",
            "安全与人工介入",
        )
    )
    candidate = (
        "- canonical_item: `UPS_FAN`\n- display_name: `UPS 风扇`\n- procurement_category: `UPS`"
    )
    content = f"# UPS风扇故障\n\n{sections.replace('有效内容。', candidate, 1)}"
    return KnowledgeDocument(
        path="knowledge/fault-guidance/ups/ups-fan-fault.md",
        metadata={
            "schema_version": 1,
            "knowledge_id": "UPS-FAN-001",
            "title": "UPS风扇故障",
            "equipment_category": "UPS",
            "knowledge_type": "FAULT_GUIDE",
            "aliases": ["FAN FAULT"],
            "risk_level": "MEDIUM",
            "status": "ACTIVE",
            "version": 1,
        },
        content=content,
        candidates=(("UPS_FAN", "UPS 风扇", "UPS"),),
    )


def test_valid_ups_fan_fixture_passes() -> None:
    categories, vocabulary = _catalogs()
    assert _validate_document(_valid_ups_fan_document(), categories, vocabulary) == []


def test_unknown_category_canonical_display_and_missing_section_fail() -> None:
    categories, vocabulary = _catalogs()
    base = _valid_ups_fan_document()
    metadata = {**base.metadata, "equipment_category": "ROW_AC"}
    content = base.content.replace("`UPS_FAN`", "`UPS_FAN_MODULE`").replace(
        "`UPS 风扇`", "`UPS 风机总成`"
    )
    content = content.replace("## 不应直接推断的内容", "## 已删除章节")
    invalid = KnowledgeDocument(
        path=base.path,
        metadata=metadata,
        content=content,
        candidates=(("UPS_FAN_MODULE", "UPS 风机总成", "UPS"),),
    )
    issues = _validate_document(invalid, categories, vocabulary)
    assert any("unknown category: ROW_AC" in issue.reason for issue in issues)
    assert any("unknown canonical_item: UPS_FAN_MODULE" in issue.reason for issue in issues)
    assert any(issue.field == "section:不应直接推断的内容" for issue in issues)


def test_display_name_mismatch_fails() -> None:
    categories, vocabulary = _catalogs()
    base = _valid_ups_fan_document()
    invalid = KnowledgeDocument(
        path=base.path,
        metadata=base.metadata,
        content=base.content.replace("UPS 风扇", "UPS 风机总成"),
        candidates=(("UPS_FAN", "UPS 风机总成", "UPS"),),
    )
    assert any(
        issue.field == "display_name"
        for issue in _validate_document(invalid, categories, vocabulary)
    )


def test_duplicate_knowledge_id_and_orphan_knowledge_fail(validation_root: Path) -> None:
    source = validation_root / "knowledge/fault-guidance/ups/ups-battery-fault.md"
    orphan = validation_root / "knowledge/fault-guidance/ups/orphan-copy.md"
    orphan.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    report = validate_repository(validation_root)
    assert any("duplicate UPS-BATTERY-001" in issue.reason for issue in report.errors)
    assert any("no Coverage entry" in issue.reason for issue in report.errors)


def test_runtime_loader_and_battery_fault_search_regression() -> None:
    root = ROOT / "knowledge/fault-guidance"
    repository = MarkdownKnowledgeLoader(root).load()
    knowledge = repository.get("UPS-BATTERY-001")
    assert knowledge is not None
    results = MarkdownKnowledgeSearch(repository).search(
        query="BATTERY FAULT", equipment_category="UPS"
    )
    assert [result.knowledge_id for result in results] == ["UPS-BATTERY-001"]
