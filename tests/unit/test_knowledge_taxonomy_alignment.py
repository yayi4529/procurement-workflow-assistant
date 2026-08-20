import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VOCABULARY = ROOT / "docs" / "task07-procurement-vocabulary-v1.md"
TAXONOMY = ROOT / "docs" / "data-center-fault-knowledge-taxonomy-v1.md"
SEED = ROOT / "backend" / "scripts" / "seed_demo_data.py"

EXPECTED_CATEGORIES = {
    "MV_SWITCHGEAR_10KV",
    "TRANSFORMER",
    "LV_SWITCHGEAR_400V",
    "UPS",
    "HVDC",
    "BATTERY",
    "CHILLER",
    "SHU",
    "COOLING_TOWER",
    "COOLING_PUMP",
    "WATER_SYSTEM",
    "IN_ROW_AC",
    "MONITORING",
    "ROOM_ENVIRONMENT",
    "TRANSMISSION",
    "SERVER",
    "OM_TOOL",
}
OBSOLETE_CATEGORIES = {"HV_SWITCHGEAR_10KV", "ROW_AC", "MAINTENANCE_TOOL"}


def _vocabulary_categories(document: str) -> list[str]:
    return re.findall(r"^## ([A-Z][A-Z0-9_]*) — ", document, flags=re.MULTILINE)


def _canonical_items(document: str) -> list[str]:
    vocabulary_body = document.split("## MV_SWITCHGEAR_10KV", maxsplit=1)[1]
    return re.findall(
        r"^\| `([A-Z][A-Z0-9_]*)` \|",
        vocabulary_body,
        flags=re.MULTILINE,
    )


def _coverage_matrix(document: str) -> str:
    return document.split("## 10. Knowledge Coverage Matrix", maxsplit=1)[1].split(
        "## 11. Priority", maxsplit=1
    )[0]


def test_vocabulary_uses_the_seventeen_unique_backend_category_codes() -> None:
    vocabulary = VOCABULARY.read_text(encoding="utf-8")
    categories = _vocabulary_categories(vocabulary)
    assert len(categories) == 17
    assert len(categories) == len(set(categories))
    assert set(categories) == EXPECTED_CATEGORIES
    assert set(categories).isdisjoint(OBSOLETE_CATEGORIES)

    seed = SEED.read_text(encoding="utf-8")
    level_two_block = seed.split("types = [", maxsplit=1)[1].split("]", maxsplit=1)[0]
    seed_codes = set(re.findall(r'\(\d+, \d+, "([A-Z0-9_]+)"', level_two_block))
    assert seed_codes == EXPECTED_CATEGORIES


def test_vocabulary_canonical_items_are_unique_and_fully_covered() -> None:
    canonical_items = _canonical_items(VOCABULARY.read_text(encoding="utf-8"))
    assert len(canonical_items) == 108
    assert len(canonical_items) == len(set(canonical_items))

    taxonomy = _coverage_matrix(TAXONOMY.read_text(encoding="utf-8"))
    matrix_items = re.findall(
        r"^\| `[A-Z0-9_]+` \| `[A-Z0-9_]+` \| .*? \| `([A-Z][A-Z0-9_]*)` \|",
        taxonomy,
        flags=re.MULTILINE,
    )
    assert set(matrix_items) == set(canonical_items)


def test_taxonomy_covers_every_category_and_preserves_existing_knowledge() -> None:
    taxonomy = _coverage_matrix(TAXONOMY.read_text(encoding="utf-8"))
    matrix_sources = set(
        re.findall(r"^\| `([A-Z][A-Z0-9_]*)` \| `[A-Z0-9_]+` \|", taxonomy, re.MULTILINE)
    )
    assert matrix_sources == EXPECTED_CATEGORIES
    assert "`UPS_BATTERY_FAULT`" in taxonomy
    assert "`UPS_BATTERY` | `BATTERY` | FAULT_DRIVEN" in taxonomy
    assert "knowledge/fault-guidance/ups/ups-battery-fault.md | EXISTING" in taxonomy
