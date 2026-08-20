import re

_BRAND_ALIASES = {
    "华为": "HUAWEI",
    "HUAWEI": "HUAWEI",
}
_MODEL_SEPARATORS = re.compile(r"[\s\-_/]+")
_ITEM_SEPARATORS = re.compile(r"[\s\-_/]+")


def normalize_brand(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    normalized = value.strip().upper()
    return _BRAND_ALIASES.get(normalized, normalized)


def normalize_model(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    return _MODEL_SEPARATORS.sub("", value.strip().upper())


def canonical_item_name(value: str) -> str:
    return _ITEM_SEPARATORS.sub("", value.strip().upper())
