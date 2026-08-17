from procurement_platform.application.assistant.entity_references import product_reference


def test_product_ids_prevent_same_brand_model_collision() -> None:
    first = product_reference(product_id=1, brand="A", model="M1")
    second = product_reference(product_id=2, brand="A", model="M1")
    assert first == "product:1"
    assert second == "product:2"
    assert first != second


def test_fallback_references_distinguish_null_candidates() -> None:
    first = product_reference(
        product_id=None,
        brand=None,
        model=None,
        device_name="UPS",
        fallback_discriminator="2026-01-01T00:00:00Z",
    )
    second = product_reference(
        product_id=None,
        brand=None,
        model=None,
        device_name="UPS",
        fallback_discriminator="2026-02-01T00:00:00Z",
    )
    assert first.startswith("product:fallback:")
    assert second.startswith("product:fallback:")
    assert first != second
