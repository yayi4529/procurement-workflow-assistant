from pathlib import Path

import yaml

from scripts.validate_fault_knowledge import validate_repository

ROOT = Path(__file__).resolve().parents[2]


def _coverage(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_repository_catalog_is_valid_and_covers_all_vocabulary() -> None:
    report = validate_repository(ROOT)
    assert report.errors == ()
    assert report.categories == 17
    assert report.coverage_entries == 109
    assert report.canonical_items_referenced == 108
    assert report.knowledge_files == 16


def test_cross_category_ups_battery_mapping_is_valid() -> None:
    catalog = _coverage(ROOT / "knowledge/catalog/fault-knowledge-coverage-v1.yaml")
    entries = catalog["entries"]
    assert isinstance(entries, list)
    entry = next(item for item in entries if item["fault_topic_id"] == "UPS_BATTERY_FAULT")
    assert entry["source_category"] == "UPS"
    assert entry["candidate_items"] == [
        {"canonical_item": "UPS_BATTERY", "procurement_category": "BATTERY"}
    ]
    assert entry["status"] == "EXISTING"


def test_existing_coverage_missing_file_fails(validation_root: Path) -> None:
    path = validation_root / "knowledge/catalog/fault-knowledge-coverage-v1.yaml"
    catalog = _coverage(path)
    entries = catalog["entries"]
    assert isinstance(entries, list)
    existing = next(item for item in entries if item["status"] == "EXISTING")
    existing["planned_knowledge_file"] = "knowledge/fault-guidance/ups/missing.md"
    path.write_text(yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), encoding="utf-8")
    report = validate_repository(validation_root)
    assert any("EXISTING file does not exist" in issue.reason for issue in report.errors)


def test_candidate_mismatch_fails(validation_root: Path) -> None:
    path = validation_root / "knowledge/catalog/fault-knowledge-coverage-v1.yaml"
    catalog = _coverage(path)
    entries = catalog["entries"]
    assert isinstance(entries, list)
    existing = next(item for item in entries if item["status"] == "EXISTING")
    existing["candidate_items"] = [
        {"canonical_item": "SERVER_HDD", "procurement_category": "SERVER"}
    ]
    path.write_text(yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), encoding="utf-8")
    report = validate_repository(validation_root)
    assert any(
        issue.field == "candidate_items" and "SERVER_HDD" in issue.reason for issue in report.errors
    )
