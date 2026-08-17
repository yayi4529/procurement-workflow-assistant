"""Stable, non-authoritative references for assistant candidate selection."""

from hashlib import sha256


def product_reference(
    *,
    product_id: int | None,
    device_profession: str | None = None,
    device_name: str = "",
    brand: str | None = None,
    model: str | None = None,
    fallback_discriminator: str = "",
) -> str:
    """Prefer backend identity; use a collision-resistant compatibility fallback."""
    if product_id is not None:
        return f"product:{product_id}"
    parts = (
        device_profession or "",
        device_name,
        brand or "",
        model or "",
        fallback_discriminator,
    )
    digest = sha256("\x1f".join(parts).encode()).hexdigest()[:20]
    return f"product:fallback:{digest}"
