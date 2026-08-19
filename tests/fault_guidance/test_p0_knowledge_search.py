from pathlib import Path

import pytest

from procurement_platform.adapters.knowledge import MarkdownKnowledgeLoader
from procurement_platform.application.fault_guidance import MarkdownKnowledgeSearch

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def search() -> MarkdownKnowledgeSearch:
    root = ROOT / "knowledge/fault-guidance"
    return MarkdownKnowledgeSearch(MarkdownKnowledgeLoader(root).load())


@pytest.mark.parametrize(
    ("category", "query", "knowledge_id"),
    [
        ("UPS", "FAN FAULT", "UPS-FAN-001"),
        ("BATTERY", "CELL FAILURE", "BATTERY-UPS-BATTERY-001"),
        ("SHU", "FILTER DIRTY", "SHU-FILTER-001"),
        ("COOLING_TOWER", "BELT BROKEN", "COOLING-TOWER-BELT-001"),
        ("COOLING_PUMP", "BEARING FAILURE", "COOLING-PUMP-BEARING-001"),
        ("COOLING_PUMP", "MECHANICAL SEAL LEAK", "COOLING-PUMP-MECHANICAL-SEAL-001"),
        ("IN_ROW_AC", "AIR FILTER ALARM", "IN-ROW-AC-FILTER-001"),
        ("MONITORING", "PSU FAULT", "MONITORING-POWER-SUPPLY-001"),
        (
            "ROOM_ENVIRONMENT",
            "TEMP HUMIDITY SENSOR FAULT",
            "ROOM-TEMP-HUMIDITY-SENSOR-001",
        ),
        (
            "TRANSMISSION",
            "TRANSCEIVER FAULT",
            "TRANSMISSION-OPTICAL-TRANSCEIVER-001",
        ),
        ("SERVER", "DIMM ERROR", "SERVER-MEMORY-001"),
        ("SERVER", "SSD FAILURE", "SERVER-SSD-001"),
        ("SERVER", "HDD FAILURE", "SERVER-HDD-001"),
        ("SERVER", "PSU FAILURE", "SERVER-POWER-SUPPLY-001"),
        ("SERVER", "FAN FAILURE", "SERVER-FAN-001"),
    ],
)
def test_every_new_p0_knowledge_has_a_representative_search_query(
    search: MarkdownKnowledgeSearch,
    category: str,
    query: str,
    knowledge_id: str,
) -> None:
    results = search.search(query=query, equipment_category=category)
    assert results
    assert results[0].knowledge_id == knowledge_id


@pytest.mark.parametrize(
    ("category", "expected"),
    [("UPS", "UPS-FAN-001"), ("SERVER", "SERVER-FAN-001")],
)
def test_common_fan_alias_isolated_by_equipment_category(
    search: MarkdownKnowledgeSearch, category: str, expected: str
) -> None:
    results = search.search(query="FAN FAULT", equipment_category=category)
    assert [result.knowledge_id for result in results] == [expected]


def test_global_search_preserves_existing_alias_behavior(
    search: MarkdownKnowledgeSearch,
) -> None:
    results = search.search(query="DIMM ERROR", equipment_category=None)
    assert results[0].knowledge_id == "SERVER-MEMORY-001"


def test_irrelevant_office_query_does_not_match_fault_knowledge(
    search: MarkdownKnowledgeSearch,
) -> None:
    assert search.search(query="办公室打印机没墨了", equipment_category=None) == []


def test_loader_loads_existing_and_all_new_p0_knowledge() -> None:
    root = ROOT / "knowledge/fault-guidance"
    loaded = MarkdownKnowledgeLoader(root).load().list_all()
    assert len(loaded) == 16
