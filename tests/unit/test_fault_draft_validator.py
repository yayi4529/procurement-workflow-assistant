from decimal import Decimal

import pytest

from procurement_platform.application.fault_guidance import FaultDraftValidator
from procurement_platform.domain.enums import (
    PurchaseItemKind,
    ValidationStatus,
)
from procurement_platform.domain.fault_guidance import CandidateItem


def _candidate(
    *,
    item_kind: PurchaseItemKind | None = PurchaseItemKind.COMPONENT,
    item_name: str = "蓄电池",
    quantity: Decimal | None = Decimal("3"),
    unit: str | None = "块",
    quantity_evidence: str | None = "USER_CONFIRMED",
) -> CandidateItem:
    return CandidateItem(
        item_kind=item_kind,
        item_name=item_name,
        quantity=quantity,
        unit=unit,
        quantity_evidence=quantity_evidence,
    )


@pytest.mark.parametrize("evidence", ["USER_CONFIRMED", "USER_EXPLICIT_REQUEST", "BACKEND_FACT"])
def test_valid_candidate_item(evidence: str) -> None:
    result = FaultDraftValidator().validate(_candidate(quantity_evidence=evidence))
    assert result.status is ValidationStatus.VALID
    assert result.missing_fields == []
    assert result.errors == []


@pytest.mark.parametrize(
    ("overrides", "missing_field"),
    [
        ({"quantity": None, "quantity_evidence": None}, "quantity"),
        ({"unit": None}, "unit"),
        ({"unit": " "}, "unit"),
    ],
)
def test_candidate_needs_clarification(overrides: dict[str, object], missing_field: str) -> None:
    if "quantity" in overrides:
        candidate = _candidate(quantity=None, quantity_evidence=None)
    else:
        unit = overrides["unit"]
        assert unit is None or isinstance(unit, str)
        candidate = _candidate(unit=unit)
    result = FaultDraftValidator().validate(candidate)
    assert result.status is ValidationStatus.NEEDS_CLARIFICATION
    assert result.missing_fields == [missing_field]
    assert result.errors == []


@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("-1")])
def test_non_positive_quantity_is_invalid(quantity: Decimal) -> None:
    result = FaultDraftValidator().validate(_candidate(quantity=quantity))
    assert result.status is ValidationStatus.INVALID
    assert result.errors == ["quantity_must_be_positive"]


def test_inferred_quantity_evidence_requires_user_clarification() -> None:
    result = FaultDraftValidator().validate(_candidate(quantity_evidence="LLM_INFERRED"))
    assert result.status is ValidationStatus.NEEDS_CLARIFICATION
    assert result.missing_fields == ["quantity"]
    assert result.errors == []


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"item_name": ""}, "item_name_required"),
        ({"item_name": " "}, "item_name_required"),
        ({"item_kind": None}, "item_kind_required"),
    ],
)
def test_required_identity_fields_are_invalid(overrides: dict[str, object], error: str) -> None:
    if "item_kind" in overrides:
        candidate = _candidate(item_kind=None)
    else:
        candidate = _candidate(item_name=str(overrides["item_name"]))
    result = FaultDraftValidator().validate(candidate)
    assert result.status is ValidationStatus.INVALID
    assert result.errors == [error]
