from pathlib import Path

import yaml

from scripts.validate_fault_knowledge import (
    OBSOLETE_CATEGORIES,
    load_backend_categories,
    load_vocabulary,
)

ROOT = Path(__file__).resolve().parents[2]


def test_machine_vocabulary_is_unique_complete_and_aligned_to_backend() -> None:
    categories = load_backend_categories(ROOT / "backend/scripts/seed_demo_data.py")
    vocabulary, issues = load_vocabulary(ROOT / "knowledge/catalog/procurement-vocabulary-v1.yaml")
    assert issues == []
    assert len(categories) == 17
    assert categories.isdisjoint(OBSOLETE_CATEGORIES)
    assert len(vocabulary) == 108
    assert {item["category"] for item in vocabulary.values()} == categories


def test_vocabulary_rejects_duplicate_item_empty_display_and_invalid_aliases(
    tmp_path: Path,
) -> None:
    path = tmp_path / "vocabulary.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "categories": {
                    "UPS": [
                        {
                            "canonical_item": "UPS_FAN",
                            "display_name": "",
                            "aliases": [],
                        },
                        {
                            "canonical_item": "UPS_FAN",
                            "display_name": "UPS 风扇",
                            "aliases": ["UPS风机"],
                        },
                    ]
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    _, issues = load_vocabulary(path)
    reasons = [issue.reason for issue in issues]
    assert any("duplicate UPS_FAN" in reason for reason in reasons)
    assert any("non-empty" in reason for reason in reasons)
