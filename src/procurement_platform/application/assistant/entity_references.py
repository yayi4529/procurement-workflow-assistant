"""Stable, non-authoritative references for assistant candidate selection."""

from hashlib import sha256


def asset_reference(asset_id: int) -> str:
    if asset_id <= 0:
        raise ValueError("asset_id must be positive")
    return f"asset:{asset_id}"


def model_reference(model_id: int) -> str:
    if model_id <= 0:
        raise ValueError("model_id must be positive")
    return f"model:{model_id}"


def parse_asset_reference(reference: str) -> int:
    prefix, separator, raw_id = reference.partition(":")
    if prefix != "asset" or not separator or not raw_id.isdecimal() or int(raw_id) <= 0:
        raise ValueError("invalid asset reference")
    return int(raw_id)


def requirement_reference(requirement_id: int) -> str:
    if requirement_id <= 0:
        raise ValueError("requirement_id must be positive")
    return f"requirement:{requirement_id}"


def parse_requirement_reference(reference: str) -> int:
    prefix, separator, raw_id = reference.partition(":")
    if prefix != "requirement" or not separator or not raw_id.isdecimal() or int(raw_id) <= 0:
        raise ValueError("invalid requirement reference")
    return int(raw_id)


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
