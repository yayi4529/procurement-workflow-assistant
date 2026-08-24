import json

from procurement_platform.application.assistant.agent import _with_candidate_draft_items
from procurement_platform.domain.requirement import SelectedProduct


def test_selected_candidate_overlays_brand_model_and_preserves_original_quantity() -> None:
    selected = SelectedProduct(
        product_key="legacy-product:1",
        item_name="开关电源",
        brand="Honeywell",
        model="MPS-A120-24",
    )

    merged = _with_candidate_draft_items(
        {
            "items_json": json.dumps(
                [{"item_name": "开关电源", "quantity": 1, "item_kind": "EQUIPMENT"}],
                ensure_ascii=False,
            ),
            "selected_candidate_json": selected.model_dump_json(),
        }
    )

    assert json.loads(str(merged["items_json"])) == [
        {
            "item_name": "开关电源",
            "quantity": 1,
            "item_kind": "EQUIPMENT",
            "equipment_category_id": None,
            "equipment_model_id": None,
            "brand": "Honeywell",
            "model": "MPS-A120-24",
        }
    ]
